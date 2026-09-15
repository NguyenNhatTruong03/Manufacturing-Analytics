-- MART: mart_whatif_pm_reduction — phuc vu cau hoi #10: neu giam 15% thoi
-- gian dung do PM (bao duong dinh ky) thi nha may chay them bao nhieu gio
-- va san xuat them bao nhieu san pham.
--
-- Cong thuc what-if (theo plan Muc 3 #10):
--   pm_giam           = pm_downtime_min * 0.15
--   gio chay them     = pm_giam / 60
--   throughput binh quan = total_biscuits_made / (run_time_min/60)  [san pham/gio chay]
--   san luong them    = gio chay them * throughput binh quan
-- Grain: 1 dong = 1 may.
with machine_level as (
    select
        machine,
        sum(pm_downtime_min)                                  as pm_downtime_min,
        sum(run_time_min)                                     as run_time_min,
        sum(total_biscuits_made)                              as total_biscuits_made
    from {{ ref('fact_oee_daily') }}
    group by 1
)

select
    machine,
    pm_downtime_min,
    pm_downtime_min * 0.15                                    as pm_downtime_reduced_min,
    pm_downtime_min * 0.15 / 60                               as extra_run_hours,
    total_biscuits_made / nullif(run_time_min / 60, 0)        as avg_throughput_per_hour,
    (pm_downtime_min * 0.15 / 60)
        * (total_biscuits_made / nullif(run_time_min / 60, 0)) as extra_products_estimated
from machine_level
