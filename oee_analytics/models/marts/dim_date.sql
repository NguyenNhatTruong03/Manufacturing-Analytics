-- MART: dim_date — date spine thang 07/2021 (phuc vu cau hoi #8:
-- xu the theo ngay trong tuan / cuoi tuan).
with spine as (
    {{ dbt_utils.date_spine(
        datepart="day",
        start_date="cast('2021-07-01' as date)",
        end_date="cast('2021-08-01' as date)"
    ) }}
)

select
    cast(date_day as date)                          as date_key,
    extract(isodow from date_day)::int              as day_of_week_iso,   -- 1=Mon .. 7=Sun
    trim(to_char(date_day, 'Day'))                  as day_name,
    extract(day from date_day)::int                 as day_of_month,
    (extract(isodow from date_day) in (6, 7))       as is_weekend,
    ((extract(day from date_day)::int - 1) / 7) + 1 as week_of_month,
    to_char(date_day, 'YYYY-MM')                    as year_month
from spine
