-- Fakta harian COVID-19 per provinsi untuk analisis tren di dashboard.
-- Incremental: run berikutnya hanya memproses tanggal yang lebih baru dari
-- tanggal terakhir yang sudah ada di tabel.

{{
    config(
        materialized='incremental',
        incremental_strategy='delete+insert',
        unique_key=['province_code', 'report_date']
    )
}}

with daily as (

    select * from {{ ref('stg_covid_daily') }}

    {% if is_incremental() %}
    where report_date > (select coalesce(max(report_date), date '1900-01-01') from {{ this }})
    {% endif %}

)

select
    report_date,
    province_code,
    bps_province_code,
    province_name,
    island,
    population,
    new_cases,
    new_deaths,
    new_recovered,
    total_cases,
    total_deaths,
    total_recovered,
    total_active_cases,
    round(new_cases * 100000.0 / population, 4) as new_cases_per_100k

from daily
