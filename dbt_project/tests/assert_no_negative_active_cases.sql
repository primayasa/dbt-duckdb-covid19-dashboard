-- Kasus aktif kumulatif tidak mungkin negatif. Sumber memuat ratusan baris
-- seperti itu; staging harus sudah menetralkannya menjadi NULL.
-- Test gagal bila masih ada baris yang lolos.

select
    report_date,
    province_code,
    total_active_cases
from {{ ref('stg_covid_daily') }}
where total_active_cases < 0
