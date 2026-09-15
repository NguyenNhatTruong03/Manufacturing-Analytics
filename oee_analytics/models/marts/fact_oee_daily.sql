-- MART: fact_oee_daily — grain: 1 dong = Machine + Product + Ngay.
-- Bang loi de tinh OEE va tra loi phan lon 10 cau hoi.
--
-- Cong thuc (ban chinh sua 2026-09-15 theo chi thi cua nguoi duyet):
--   planned_time_min = tong duration, TRU dong outlier > 1440 phut,
--                      VA TRU 'NO (No Order)' — NO la Schedule Loss theo
--                      Lean OEE, loai khoi mau so, khong cong vao Downtime
--   downtime_min     = tong thoi gian CC (CHANGEOVER) + PM (PLANNED_DOWNTIME_PM)
--   run_time_min     = planned_time_min - downtime_min  (SUy RA, khong dung
--                      literal 'Run Time' — nhan nay chi co 9/8,044 dong)
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
    d.downtime_min,
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
