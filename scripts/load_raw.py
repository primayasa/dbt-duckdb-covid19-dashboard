"""Memuat output pipeline Airflow (Tugas ETL sebelumnya) ke schema ``raw`` DuckDB.

Dua file CSV hasil DAG ``etl_sederhana_574012`` dimuat apa adanya (semua kolom
sebagai teks, nama kolom asli) supaya pembersihan tipe data, nama kolom, dan
format tanggal dikerjakan staging model dbt.

Script ini idempotent: tabel raw selalu dibuat ulang (CREATE OR REPLACE).
"""

import os
from pathlib import Path

import duckdb

PROJECT_ROOT = Path(__file__).resolve().parent.parent
AIRFLOW_OUTPUT_DIR = PROJECT_ROOT / "data" / "airflow_output"
WAREHOUSE_PATH = Path(
    os.environ.get("DUCKDB_PATH", PROJECT_ROOT / "data" / "warehouse.duckdb")
)

# nama tabel raw -> file CSV output Airflow
RAW_TABLES = {
    # hasil task extract_data >> validate_data (harian, tingkat provinsi)
    "covid_daily": "covid_extracted.csv",
    # hasil task load_data (ringkasan bulanan per provinsi)
    "covid_monthly_summary": "covid_provinsi_monthly_summary.csv",
}


def load_raw_tables():
    """Membuat schema ``raw`` dan memuat ulang setiap tabel raw dari CSV."""
    WAREHOUSE_PATH.parent.mkdir(parents=True, exist_ok=True)
    connection = duckdb.connect(str(WAREHOUSE_PATH))
    try:
        connection.execute("create schema if not exists raw")
        for table_name, csv_name in RAW_TABLES.items():
            csv_path = AIRFLOW_OUTPUT_DIR / csv_name
            connection.execute(
                f"create or replace table raw.{table_name} as "
                "select * from read_csv(?, header = true, all_varchar = true)",
                [str(csv_path)],
            )
            row_count = connection.execute(
                f"select count(*) from raw.{table_name}"
            ).fetchone()[0]
            print(f"raw.{table_name}: {row_count} baris <- {csv_path.name}")
    finally:
        connection.close()


if __name__ == "__main__":
    load_raw_tables()
