-- Staging data harian COVID-19 per provinsi (output extract/validate Airflow).
-- Merapikan nama kolom, tipe data, format tanggal, dan nilai kumulatif yang
-- mustahil secara logika, lalu melengkapi kode provinsi BPS dari seed.

with source as (

    select * from {{ source('raw', 'covid_daily') }}

),

renamed as (

    select
        -- kunci
        strptime("Date", '%m/%d/%Y')::date              as report_date,
        "Location ISO Code"                             as province_code,
        trim("Province")                                as province_name,
        "Island"                                        as island,

        -- atribut provinsi
        "Population"::bigint                            as population,
        "Area (km2)"::bigint                            as area_km2,
        "Longitude"::double                             as longitude,
        "Latitude"::double                              as latitude,

        -- angka harian
        "New Cases"::bigint                             as new_cases,
        "New Deaths"::bigint                            as new_deaths,
        "New Recovered"::bigint                         as new_recovered,

        -- angka kumulatif dari sumber
        "Total Cases"::bigint                           as total_cases,
        "Total Deaths"::bigint                          as total_deaths,
        "Total Recovered"::bigint                       as total_recovered,
        "Total Active Cases"::bigint                    as source_total_active_cases,

        -- persentase tersimpan sebagai teks ("51.28%") di sumber
        replace("Case Fatality Rate", '%', '')::double  as source_case_fatality_rate_pct,
        replace("Case Recovered Rate", '%', '')::double as source_case_recovered_rate_pct

    from source

),

province_codes as (

    select * from {{ ref('province_bps_codes') }}

),

cleaned as (

    select
        renamed.* exclude (source_total_active_cases),

        -- kode provinsi BPS, kunci wilayah untuk peta di dashboard
        province_codes.bps_province_code,

        -- kasus aktif tidak mungkin negatif: nilai mustahil dijadikan NULL
        case
            when source_total_active_cases >= 0 then source_total_active_cases
        end                                             as total_active_cases,

        -- penanda baris yang angka kumulatif sumbernya tidak konsisten
        (source_total_active_cases >= 0)                as is_cumulative_consistent

    from renamed
    left join province_codes
        on renamed.province_code = province_codes.province_code

)

select * from cleaned
