FROM python:3.12-slim

COPY requirements.txt /tmp/requirements.txt
RUN pip install --no-cache-dir -r /tmp/requirements.txt

# dbt dijalankan sebagai user host (lihat docker-compose.yml), jadi HOME harus bisa ditulis
ENV HOME=/tmp
WORKDIR /workspace
