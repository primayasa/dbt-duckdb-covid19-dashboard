-- Agregasi bulanan dbt harus sama persis dengan ringkasan bulanan yang
-- dihasilkan pipeline Airflow. Test gagal bila ada provinsi-bulan yang
-- angkanya berbeda atau tidak punya pasangan di output Airflow.

select
    province_month_key,
    new_cases,
    airflow_new_cases
from {{ ref('mart_covid_monthly_province') }}
where not is_reconciled_with_airflow
