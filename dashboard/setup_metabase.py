"""Menyiapkan Metabase dari nol lewat REST API: akun admin, koneksi DuckDB,
kartu (KPI, chart, dan peta), serta dashboard tiga tab beserta filternya.

Script ini idempotent: bila dashboard dengan nama yang sama sudah ada, tidak
ada yang dibuat ulang. Hanya memakai standard library supaya bisa dijalankan
di image dbt tanpa dependensi tambahan.

Setelah dashboard terbentuk, definisinya diekspor ke
``dashboard/metabase_dashboard_export.json``.
"""

import json
import os
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

MB_URL = os.environ.get("MB_URL", "http://localhost:3000").rstrip("/")
ADMIN_EMAIL = os.environ.get("MB_ADMIN_EMAIL") or "admin@tugas.local"
ADMIN_PASSWORD = os.environ.get("MB_ADMIN_PASSWORD") or "Tugas574012!"
DUCKDB_PATH = os.environ.get("MB_DUCKDB_PATH", "/data/warehouse.duckdb")

DATABASE_NAME = "Warehouse DuckDB"
COLLECTION_NAME = "Tugas dbt dan BI 574012"
DASHBOARD_NAME = "COVID-19 Indonesia"
MONTHLY_TABLE = "mart_covid_monthly_province"
DAILY_TABLE = "mart_covid_daily_province"
EXPORT_PATH = Path(__file__).resolve().parent / "metabase_dashboard_export.json"

# Peta provinsi: Metabase hanya menerima GeoJSON dari URL publik (alamat
# internal container ditolak). Properti "kode" pada file ini adalah kode
# provinsi BPS, dicocokkan dengan kolom bps_province_code pada mart.
MAP_ID = "indonesia_provinsi"
MAP_GEOJSON_URL = os.environ.get("MB_GEOJSON_URL") or (
    "https://raw.githubusercontent.com/ans-4175/peta-indonesia-geojson/"
    "master/indonesia-prov.geojson"
)
MAP_REGION_KEY = "kode"
MAP_REGION_NAME = "Propinsi"

# biru = kasus (jumlah maupun per penduduk), merah = kematian dan CFR
COLOR_CASES = "#2E6FB7"
COLOR_DEATHS = "#C0392B"
# gradasi peta: makin tua warnanya, makin tinggi nilainya
MAP_COLORS_CASES = ["#E6EEF8", "#BBD2EC", "#8FB5DF", "#5F94CE", "#2E6FB7", "#1B4A80"]
MAP_COLORS_DEATHS = ["#FCE8E6", "#F7C4BE", "#EE9A90", "#E06B5E", "#C0392B", "#7F1D14"]

session_id = None


def api(method, path, body=None):
    """Memanggil endpoint Metabase dan mengembalikan respons JSON."""
    headers = {"Content-Type": "application/json"}
    if session_id:
        headers["X-Metabase-Session"] = session_id
    request = urllib.request.Request(
        f"{MB_URL}/api/{path}",
        data=json.dumps(body).encode() if body is not None else None,
        headers=headers,
        method=method,
    )
    try:
        with urllib.request.urlopen(request, timeout=120) as response:
            payload = response.read()
    except urllib.error.HTTPError as error:
        detail = error.read().decode(errors="replace")
        raise RuntimeError(f"{method} {path} -> {error.code}: {detail}") from error
    return json.loads(payload) if payload else None


def wait_until_healthy(timeout_seconds=600):
    """Menunggu sampai Metabase selesai inisialisasi."""
    deadline = time.time() + timeout_seconds
    while time.time() < deadline:
        try:
            if api("GET", "health").get("status") == "ok":
                return
        except (RuntimeError, urllib.error.URLError, ConnectionError, OSError):
            pass
        time.sleep(5)
    raise TimeoutError("Metabase tidak kunjung siap")


def login_or_setup():
    """Membuat akun admin pada instalasi baru, atau login bila sudah ada."""
    global session_id
    properties = api("GET", "session/properties")
    if properties.get("has-user-setup"):
        session = api(
            "POST", "session", {"username": ADMIN_EMAIL, "password": ADMIN_PASSWORD}
        )
    else:
        session = api(
            "POST",
            "setup",
            {
                "token": properties["setup-token"],
                "user": {
                    "first_name": "Wahyu",
                    "last_name": "Primayasa",
                    "email": ADMIN_EMAIL,
                    "password": ADMIN_PASSWORD,
                    "site_name": "Tugas dbt dan BI Dashboard 574012",
                },
                "prefs": {
                    "site_name": "Tugas dbt dan BI Dashboard 574012",
                    "site_locale": "en",
                    "allow_tracking": False,
                },
            },
        )
    session_id = session["id"]


def as_list(response):
    """Sebagian endpoint list membungkus hasilnya di dalam kunci ``data``."""
    return response["data"] if isinstance(response, dict) else response


def ensure_database():
    """Mendaftarkan warehouse.duckdb (read-only) dan mengembalikan id-nya."""
    for database in as_list(api("GET", "database")):
        if database["name"] == DATABASE_NAME:
            return database["id"]
    database = api(
        "POST",
        "database",
        {
            "name": DATABASE_NAME,
            "engine": "duckdb",
            "details": {
                "database_file": DUCKDB_PATH,
                "read_only": True,
                "old_implicit_casting": True,
            },
            "is_full_sync": True,
        },
    )
    return database["id"]


def wait_for_tables(database_id, timeout_seconds=300):
    """Menunggu sinkronisasi schema, lalu memetakan tabel mart ke id field."""
    api("POST", f"database/{database_id}/sync_schema")
    deadline = time.time() + timeout_seconds
    while time.time() < deadline:
        metadata = api("GET", f"database/{database_id}/metadata")
        tables = {
            table["name"]: {
                "id": table["id"],
                "fields": {field["name"]: field["id"] for field in table["fields"]},
            }
            for table in metadata["tables"]
            if table["name"] in (MONTHLY_TABLE, DAILY_TABLE)
        }
        # tunggu sampai kolom kunci peta ikut tersinkron
        if len(tables) == 2 and all(
            "bps_province_code" in table["fields"] for table in tables.values()
        ):
            return tables
        time.sleep(5)
    raise TimeoutError("Tabel mart belum muncul di Metabase; sudahkah dbt run?")


def ensure_province_map():
    """Mendaftarkan peta provinsi Indonesia sebagai custom map Metabase."""
    api(
        "PUT",
        "setting/custom-geojson",
        {
            "value": {
                MAP_ID: {
                    "name": "Indonesia (provinsi)",
                    "url": MAP_GEOJSON_URL,
                    "region_key": MAP_REGION_KEY,
                    "region_name": MAP_REGION_NAME,
                }
            }
        },
    )


def ensure_collection():
    """Membuat collection khusus tugas dan mengembalikan id-nya."""
    for collection in api("GET", "collection"):
        if collection.get("name") == COLLECTION_NAME and not collection.get("archived"):
            return collection["id"]
    return api("POST", "collection", {"name": COLLECTION_NAME})["id"]


def find_dashboard(collection_id):
    """Mengembalikan id dashboard tugas bila sudah pernah dibuat."""
    for dashboard in as_list(api("GET", "dashboard")):
        if (
            dashboard["name"] == DASHBOARD_NAME
            and dashboard.get("collection_id") == collection_id
            and not dashboard.get("archived")
        ):
            return dashboard["id"]
    return None


def field(table, column, **options):
    """Referensi field MBQL."""
    return ["field", table["fields"][column], options or None]


def named(aggregation, name, display_name):
    """Memberi nama kolom pada sebuah agregasi MBQL."""
    return [
        "aggregation-options",
        aggregation,
        {"name": name, "display-name": display_name},
    ]


def build_card_definitions(monthly, daily):
    """Daftar kartu: (kunci, nama, tabel, display, query MBQL, pengaturan visual)."""
    cases = named(["sum", field(monthly, "new_cases")], "kasus", "Kasus")
    deaths = named(["sum", field(monthly, "new_deaths")], "kematian", "Kematian")
    recovered = named(["sum", field(monthly, "new_recovered")], "sembuh", "Sembuh")
    fatality_rate = named(
        [
            "*",
            ["/", ["sum", field(monthly, "new_deaths")], ["sum", field(monthly, "new_cases")]],
            100,
        ],
        "cfr",
        "CFR (%)",
    )
    cases_per_100k = named(
        [
            "/",
            ["*", ["sum", field(monthly, "new_cases")], 100000],
            ["max", field(monthly, "population")],
        ],
        "kasus_per_100rb",
        "Kasus per 100 ribu penduduk",
    )
    percent_format = {"suffix": "%", "decimals": 2}
    by_province = [field(monthly, "province_name")]
    week = [field(daily, "report_date", **{"temporal-unit": "week"})]

    def top_provinces(aggregation, metric_name, color):
        query = {
            "aggregation": [aggregation],
            "breakout": by_province,
            "order-by": [["desc", ["aggregation", 0]]],
            "limit": 10,
        }
        settings = {
            "graph.dimensions": ["province_name"],
            "graph.metrics": [metric_name],
            "graph.x_axis.title_text": "",
            "graph.y_axis.title_text": "",
            "graph.show_values": True,
            "series_settings": {metric_name: {"color": color}},
        }
        return query, settings

    def weekly_trend(column, metric_name, label, color):
        query = {
            "aggregation": [named(["sum", field(daily, column)], metric_name, label)],
            "breakout": week,
        }
        settings = {
            "graph.dimensions": ["report_date"],
            "graph.metrics": [metric_name],
            "graph.x_axis.title_text": "",
            "graph.y_axis.title_text": label,
            "series_settings": {metric_name: {"color": color}},
        }
        return query, settings

    def province_map(aggregation, metric_name, colors):
        query = {
            "aggregation": [aggregation],
            "breakout": [field(monthly, "bps_province_code")],
        }
        settings = {
            "map.type": "region",
            "map.region": MAP_ID,
            "map.dimension": "bps_province_code",
            "map.metric": metric_name,
            "map.colors": colors,
        }
        return query, settings

    # peta menampilkan ukuran yang sama dengan dua chart top-10 di tab 2,
    # tetapi untuk seluruh provinsi
    map_cfr_query, map_cfr_settings = province_map(fatality_rate, "cfr", MAP_COLORS_DEATHS)
    map_cfr_settings["column_settings"] = {'["name","cfr"]': percent_format}
    map_rate_query, map_rate_settings = province_map(
        cases_per_100k, "kasus_per_100rb", MAP_COLORS_CASES
    )
    map_rate_settings["column_settings"] = {'["name","kasus_per_100rb"]': {"decimals": 0}}
    top_cases_query, top_cases_settings = top_provinces(cases, "kasus", COLOR_CASES)
    top_cfr_query, top_cfr_settings = top_provinces(fatality_rate, "cfr", COLOR_DEATHS)
    top_cfr_settings["column_settings"] = {'["name","cfr"]': percent_format}
    top_rate_query, top_rate_settings = top_provinces(
        cases_per_100k, "kasus_per_100rb", COLOR_CASES
    )
    top_rate_settings["column_settings"] = {'["name","kasus_per_100rb"]': {"decimals": 0}}
    weekly_cases_query, weekly_cases_settings = weekly_trend(
        "new_cases", "kasus", "Kasus baru per minggu", COLOR_CASES
    )
    weekly_deaths_query, weekly_deaths_settings = weekly_trend(
        "new_deaths", "kematian", "Kematian baru per minggu", COLOR_DEATHS
    )

    return [
        ("kpi_cases", "Total kasus terkonfirmasi", monthly, "scalar",
         {"aggregation": [cases]}, {}),
        ("kpi_deaths", "Total kematian", monthly, "scalar",
         {"aggregation": [deaths]}, {}),
        ("kpi_recovered", "Total sembuh", monthly, "scalar",
         {"aggregation": [recovered]}, {}),
        ("kpi_cfr", "Case fatality rate", monthly, "scalar",
         {"aggregation": [fatality_rate]},
         {"column_settings": {'["name","cfr"]': percent_format}}),
        ("weekly_cases", "Kasus baru per minggu", daily, "line",
         weekly_cases_query, weekly_cases_settings),
        ("weekly_deaths", "Kematian baru per minggu", daily, "line",
         weekly_deaths_query, weekly_deaths_settings),
        ("top_cases", "10 provinsi dengan kasus terbanyak", monthly, "row",
         top_cases_query, top_cases_settings),
        ("island_cases", "Kasus menurut pulau", monthly, "bar",
         {
             "aggregation": [cases],
             "breakout": [field(monthly, "island")],
             "order-by": [["desc", ["aggregation", 0]]],
         },
         {
             "graph.dimensions": ["island"],
             "graph.metrics": ["kasus"],
             "graph.x_axis.title_text": "",
             "graph.y_axis.title_text": "",
             "graph.show_values": True,
             "series_settings": {"kasus": {"color": COLOR_CASES}},
         }),
        ("top_cfr", "10 provinsi dengan CFR tertinggi", monthly, "row",
         top_cfr_query, top_cfr_settings),
        ("top_rate", "10 provinsi dengan kasus per 100 ribu penduduk tertinggi",
         monthly, "row", top_rate_query, top_rate_settings),
        ("map_cfr", "Peta CFR per provinsi", monthly, "map",
         map_cfr_query, map_cfr_settings),
        ("map_rate", "Peta kasus per 100 ribu penduduk per provinsi", monthly, "map",
         map_rate_query, map_rate_settings),
        ("province_table", "Ringkasan per provinsi", monthly, "table",
         {
             "aggregation": [cases, deaths, recovered, fatality_rate, cases_per_100k],
             "breakout": [field(monthly, "province_name"), field(monthly, "island")],
             "order-by": [["desc", ["aggregation", 0]]],
         },
         {
             "column_settings": {
                 '["name","province_name"]': {"column_title": "Provinsi"},
                 '["name","island"]': {"column_title": "Pulau"},
                 '["name","cfr"]': percent_format,
                 '["name","kasus_per_100rb"]': {"decimals": 0},
             },
         }),
    ]


def create_cards(database_id, collection_id, monthly, daily):
    """Membuat seluruh kartu dan mengembalikan {kunci: (id kartu, tabel)}."""
    cards = {}
    for key, name, table, display, query, settings in build_card_definitions(
        monthly, daily
    ):
        card = api(
            "POST",
            "card",
            {
                "name": name,
                "collection_id": collection_id,
                "display": display,
                "dataset_query": {
                    "database": database_id,
                    "type": "query",
                    "query": {"source-table": table["id"], **query},
                },
                "visualization_settings": settings,
            },
        )
        cards[key] = (card["id"], table)
        print(f"kartu dibuat: {name}")
    return cards


PARAMETERS = [
    {"id": "f_pulau", "name": "Pulau", "slug": "pulau", "type": "string/=", "sectionId": "string"},
    {"id": "f_provinsi", "name": "Provinsi", "slug": "provinsi", "type": "string/=", "sectionId": "string"},
    {"id": "f_periode", "name": "Periode", "slug": "periode", "type": "date/all-options", "sectionId": "date"},
]

# (tab, kunci kartu, baris, kolom, lebar, tinggi) pada grid 24 kolom.
# Kartu top-10 harus setinggi minimal 8 baris: bila lebih pendek, Metabase
# menggabungkan batang terbawah menjadi satu batang "Other".
LAYOUT = [
    ("nasional", "kpi_cases", 0, 0, 6, 3),
    ("nasional", "kpi_deaths", 0, 6, 6, 3),
    ("nasional", "kpi_recovered", 0, 12, 6, 3),
    ("nasional", "kpi_cfr", 0, 18, 6, 3),
    ("nasional", "weekly_cases", 3, 0, 14, 7),
    ("nasional", "weekly_deaths", 10, 0, 14, 7),
    ("nasional", "top_cases", 3, 14, 10, 8),
    ("nasional", "island_cases", 11, 14, 10, 6),
    ("provinsi", "top_cfr", 0, 0, 12, 8),
    ("provinsi", "top_rate", 0, 12, 12, 8),
    ("provinsi", "province_table", 8, 0, 24, 8),
    ("peta", "map_cfr", 0, 0, 24, 9),
    ("peta", "map_rate", 9, 0, 24, 9),
]
TABS = {
    "nasional": (-1, "Ringkasan Nasional"),
    "provinsi": (-2, "Perbandingan Provinsi"),
    "peta": (-3, "Peta Sebaran"),
}


def create_dashboard(collection_id, cards):
    """Membuat dashboard beserta tab-nya dan menghubungkan filter ke setiap kartu."""
    dashboard = api(
        "POST",
        "dashboard",
        {
            "name": DASHBOARD_NAME,
            "description": (
                "Perkembangan dan sebaran COVID-19 di Indonesia, Maret 2020 "
                "sampai September 2022. Sumber: mart dbt di atas output Airflow."
            ),
            "collection_id": collection_id,
        },
    )

    dashcards = []
    for index, (tab, key, row, col, size_x, size_y) in enumerate(LAYOUT, start=1):
        card_id, table = cards[key]
        date_column = "report_month" if table["fields"].get("report_month") else "report_date"
        targets = {
            "f_pulau": field(table, "island"),
            "f_provinsi": field(table, "province_name"),
            "f_periode": field(table, date_column),
        }
        dashcards.append(
            {
                "id": -index,
                "card_id": card_id,
                "dashboard_tab_id": TABS[tab][0],
                "row": row,
                "col": col,
                "size_x": size_x,
                "size_y": size_y,
                "parameter_mappings": [
                    {
                        "parameter_id": parameter_id,
                        "card_id": card_id,
                        "target": ["dimension", target],
                    }
                    for parameter_id, target in targets.items()
                ],
                "visualization_settings": {},
            }
        )

    api(
        "PUT",
        f"dashboard/{dashboard['id']}",
        {
            "parameters": PARAMETERS,
            "tabs": [{"id": tab_id, "name": name} for tab_id, name in TABS.values()],
            "dashcards": dashcards,
        },
    )
    return dashboard["id"]


def export_dashboard(dashboard_id):
    """Menyimpan definisi dashboard (beserta kartunya) sebagai file JSON."""
    definition = api("GET", f"dashboard/{dashboard_id}")
    EXPORT_PATH.write_text(json.dumps(definition, indent=2, ensure_ascii=False) + "\n")
    print(f"definisi dashboard diekspor ke {EXPORT_PATH}")


def main():
    wait_until_healthy()
    login_or_setup()
    database_id = ensure_database()
    tables = wait_for_tables(database_id)
    ensure_province_map()
    collection_id = ensure_collection()

    dashboard_id = find_dashboard(collection_id)
    if dashboard_id is None:
        cards = create_cards(
            database_id, collection_id, tables[MONTHLY_TABLE], tables[DAILY_TABLE]
        )
        dashboard_id = create_dashboard(collection_id, cards)
        export_dashboard(dashboard_id)
        print(f"dashboard dibuat: {DASHBOARD_NAME}")
    else:
        print(f"dashboard sudah ada, tidak dibuat ulang: {DASHBOARD_NAME}")

    print(f"buka http://localhost:3000/dashboard/{dashboard_id}")
    print(f"login: {ADMIN_EMAIL} / {ADMIN_PASSWORD}")


if __name__ == "__main__":
    try:
        main()
    except Exception as error:  # noqa: BLE001 - pesan ringkas untuk log container
        print(f"setup Metabase gagal: {error}", file=sys.stderr)
        sys.exit(1)
