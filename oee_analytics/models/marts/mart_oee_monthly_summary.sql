-- MART: mart_oee_monthly_summary — phuc vu cau hoi #1: OEE trung bao toan
-- nha may thang 07/2021 so voi World Class 85%.
--
-- OEE cap thang tinh lai tu TONG cac thanh phan (weighted, chuan OEE):
--   availability = sum(run_time) / sum(planned_time)
--   performance  = sum(total_biscuits) / sum(target_biscuits)  voi
--                  target_biscuits = target_biscuits_per_hour * (run_time/60)
--                  (san luong muc tieu cho thoi gian chay thuc te), clip 100%
--   quality      = sum(good) / sum(total), clip 100%
--   oee          = a * p * q
-- Kem trung binh OEE ngay co trong so theo run_time (sum(oee*run)/sum(run))
-- de so sanh voi xuan huong theo ngay.
with monthly as (
    select
        sum(planned_time_min)    as planned_time_min,
        sum(run_time_min)        as run_time_min,
        sum(downtime_min)        as downtime_min,
        sum(changeover_time_min) as changeover_time_min,
        sum(pm_downtime_min)     as pm_downtime_min,
        sum(minor_stoppage_min)  as minor_stoppage_min,
        sum(major_stoppage_min)  as major_stoppage_min,
        sum(total_biscuits_made) as total_biscuits_made,
        sum(good_biscuits_made)  as good_biscuits_made,
        sum(coalesce(target_biscuits_per_hour, 0) * coalesce(run_time_min, 0) / 60) as target_biscuits_total,
        sum(coalesce(oee, 0) * coalesce(run_time_min, 0)) / nullif(sum(coalesce(run_time_min, 0)), 0) as oee_weighted_avg
    from {{ ref('fact_oee_daily') }}
)

select
    '2021-07'                                                                   as year_month,
    planned_time_min,
    run_time_min,
    downtime_min,
    changeover_time_min,
    pm_downtime_min,
    minor_stoppage_min,
    major_stoppage_min,
    total_biscuits_made,
    good_biscuits_made,
    run_time_min / nullif(planned_time_min, 0)                                  as availability,
    least(
        total_biscuits_made / nullif(target_biscuits_total, 0),
        1.0
    )                                                                           as performance,
    least(
        good_biscuits_made::numeric / nullif(total_biscuits_made, 0),
        1.0
    )                                                                           as quality,
    coalesce(run_time_min / nullif(planned_time_min, 0), 0)
        * least(total_biscuits_made / nullif(target_biscuits_total, 0), 1.0)
        * least(good_biscuits_made::numeric / nullif(total_biscuits_made, 0), 1.0) as oee,
    oee_weighted_avg
from monthly
