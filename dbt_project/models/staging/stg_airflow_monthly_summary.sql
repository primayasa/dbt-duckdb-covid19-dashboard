-- Staging ringkasan bulanan hasil task load_data Airflow.
-- Dipakai sebagai pembanding (rekonsiliasi) terhadap agregasi ulang di dbt.

with source as (

    select * from {{ source('raw', 'covid_monthly_summary') }}

),

renamed as (

    select
        trim("Province")                            as province_name,
        -- "YearMonth" berupa teks 'YYYY-MM' -> tanggal awal bulan
        strptime("YearMonth" || '-01', '%Y-%m-%d')::date as report_month,
        "New Cases"::bigint                         as new_cases,
        "New Deaths"::bigint                        as new_deaths,
        "New Recovered"::bigint                     as new_recovered,
        "Case Fatality Rate (%)"::double            as case_fatality_rate_pct,
        "Recovery Rate (%)"::double                 as recovery_rate_pct

    from source

)

select * from renamed
