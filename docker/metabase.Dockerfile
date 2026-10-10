# Image resmi Metabase berbasis Alpine (musl) tidak bisa memuat DuckDB,
# jadi Metabase dijalankan dari JAR di atas image JRE berbasis glibc.
FROM eclipse-temurin:21-jre

ARG METABASE_VERSION=v0.63.19
ARG DUCKDB_DRIVER_VERSION=1.5.5.0

ENV MB_PLUGINS_DIR=/app/plugins

RUN apt-get update \
    && apt-get install -y --no-install-recommends curl \
    && rm -rf /var/lib/apt/lists/* \
    && mkdir -p /app/plugins /metabase-data

# unduhan besar (sekitar 660 MB): ulangi dan lanjutkan bila koneksi terputus
RUN curl -fSL --retry 10 --retry-all-errors -C - -o /app/metabase.jar \
        "https://downloads.metabase.com/${METABASE_VERSION}/metabase.jar"
RUN curl -fSL --retry 10 --retry-all-errors -C - -o /app/plugins/duckdb.metabase-driver.jar \
        "https://github.com/motherduckdb/metabase_duckdb_driver/releases/download/${DUCKDB_DRIVER_VERSION}/duckdb.metabase-driver.jar"

WORKDIR /app
EXPOSE 3000
CMD ["java", "-jar", "/app/metabase.jar"]
