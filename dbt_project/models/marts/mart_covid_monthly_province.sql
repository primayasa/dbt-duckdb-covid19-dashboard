-- Ringkasan bulanan COVID-19 per provinsi.
-- Agregasi ulang dari staging harian, digabung (join) dengan ringkasan
-- bulanan versi Airflow untuk rekonsiliasi.

with daily as (

    select * from {{ ref('stg_covid_daily') }}

),

airflow_monthly as (

    select * from {{ ref('stg_airflow_monthly_summary') }}

),

monthly as (

    select
        date_trunc('month', report_date)::date  as report_month,
        province_code,
        bps_province_code,
        province_name,
        island,
        max(population)                         as population,
        count(*)                                as reporting_days,
        sum(new_cases)                          as new_cases,
        sum(new_deaths)                         as new_deaths,
        sum(new_recovered)                      as new_recovered

    from daily
    group by 1, 2, 3, 4, 5

),

final as (

    select
        monthly.province_code || '-' || strftime(monthly.report_month, '%Y-%m')
            as province_month_key,
        monthly.report_month,
        monthly.province_code,
        monthly.bps_province_code,
        monthly.province_name,
        monthly.island,
        monthly.population,
        monthly.reporting_days,
        monthly.new_cases,
        monthly.new_deaths,
        monthly.new_recovered,

        round(monthly.new_deaths * 100.0 / nullif(monthly.new_cases, 0), 2)
            as case_fatality_rate_pct,
        round(monthly.new_recovered * 100.0 / nullif(monthly.new_cases, 0), 2)
            as recovery_rate_pct,
        round(monthly.new_cases * 100000.0 / monthly.population, 2)
            as new_cases_per_100k,

        airflow_monthly.new_cases               as airflow_new_cases,
        coalesce(
            monthly.new_cases = airflow_monthly.new_cases
            and monthly.new_deaths = airflow_monthly.new_deaths
            and monthly.new_recovered = airflow_monthly.new_recovered,
            false
        )                                       as is_reconciled_with_airflow

    from monthly
    left join airflow_monthly
        on monthly.province_name = airflow_monthly.province_name
        and monthly.report_month = airflow_monthly.report_month

)

select * from final
