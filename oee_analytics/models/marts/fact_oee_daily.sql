-- MART: fact_oee_daily — grain: 1 dong = Machine + Product + Ngay.
-- Bang loi de tinh OEE va tra loi phan lon 10 cau hoi (theo Muc 2 cua plan).
--
-- Cong thuc (dung theo plan, khong doi):
--   planned_time_min = tong duration cua moi event trong ngay, TRU dong outlier
--   run_time_min     = tong duration khi oee_status_group = 'RUN'
--   downtime_min     = planned_time_min - run_time_min
--   availability     = run_time_min / planned_time_min
--   performance      = (total_biscuits_made / (run_time_min/60)) / target,
--                      clip tai 100% (LEAST 1.0) do nhieu sensor
--   quality          = good_biscuits_made / total_biscuits_made, clip tai 100%
--   oee              = availability * performance * quality
--
-- Xu ly NULL: neu run_time = 0 thi performance NULL; khi nhan thanh OEE,
-- nhan tu NULL duoc coi la 0 (co run_time = 0 -> khong hieu qua nao).
with daily as (
    select * from {{ ref('int_daily_machine_product') }}
)

select
    d.machine,
    d.product,
    d.event_date as date_key,
    m.machine_key,
    p.product_key,
    dd.is_weekend,
    dd.day_name,
    d.planned_time_min,
    d.run_time_min,
    d.planned_time_min - d.run_time_min as downtime_min,
    d.changeover_time_min,
    d.pm_downtime_min,
    d.minor_stoppage_min,
    d.major_stoppage_min,
    d.total_biscuits_made,
    d.good_biscuits_made,
    d.target_biscuits_per_hour,
    d.availability,
    d.performance,
    d.quality,
    coalesce(d.availability, 0) * coalesce(d.performance, 0) * coalesce(d.quality, 0) as oee
from daily d
left join {{ ref('dim_machine') }} m
    on d.machine = m.machine_name
left join {{ ref('dim_product') }} p
    on d.product = p.product_name
left join {{ ref('dim_date') }} dd
    on d.event_date = dd.date_key
