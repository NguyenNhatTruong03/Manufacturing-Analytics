-- INTERMEDIATE: aggregate theo grain (Machine, Product, Ngay) — co so cho
-- fact_oee_daily. Day la muc aggregate duy nhat ma so dem san luong IoT
-- (TotalBiscuitsMade / GoodMadeBiscuits) duoc coi la on dinh de dung:
-- o record le co 4,116/8,044 dong Good > Total (counter nhieu), nen tuyet
-- doi khong tinh Quality o muc dong le (theo Muc 0 + Muc 4 cua plan).
--
-- CONG THUC THOI GIAN (ban chinh sua 2026-09-15 theo chi thi cua nguoi duyet):
--   planned_time_min = SUM(duration) WHERE is_duration_outlier = false
--                      AND oee_category_raw != 'NO (No Order)'
--                      → NO la Schedule Loss theo Lean OEE (khong co lenh
--                        san xuat thi khong mat Availability): LOAI khoi
--                        mau so Planned Production Time, KHONG cong vao
--                        Downtime.
--   downtime_min     = SUM(duration) WHERE oee_status_group IN
--                      ('CHANGEOVER', 'PLANNED_DOWNTIME_PM')
--                      AND is_duration_outlier = false   (tuc CC + PM)
--   run_time_min     = planned_time_min - downtime_min
--                      → Run Time duoc SUY RA: moi thoi gian khong phai
--                        NO/CC/PM deu duoc coi la dang chay. KHONG dung
--                        literal 'Run Time' vi nhan nay chi xuat hien
--                        9/8,044 dong (~240 phut, 1/10 may) — khong the
--                        lam tu so Availability.
--   minor/major stoppage va tong san luong: giu nguyen dinh nghia cu
--   (tren moi su kien khong outlier, khong loai NO).
with events as (
    select *
    from {{ ref('int_events_classified') }}
    where not is_duration_outlier
),

aggregated as (
    select
        machine,
        product,
        date_trunc('day', start_datetime)::date as event_date,
        sum(case when oee_status_group <> 'NO_ORDER' then duration_minutes else 0 end)
                                                              as planned_time_min,
        sum(case when oee_status_group in ('CHANGEOVER', 'PLANNED_DOWNTIME_PM')
                 then duration_minutes else 0 end)            as downtime_min,
        sum(case when oee_status_group = 'CHANGEOVER'
                 then duration_minutes else 0 end)            as changeover_time_min,
        sum(case when oee_status_group = 'PLANNED_DOWNTIME_PM'
                 then duration_minutes else 0 end)            as pm_downtime_min,
        sum(case when stoppage_class = 'MINOR'
                 then duration_minutes else 0 end)            as minor_stoppage_min,
        sum(case when stoppage_class = 'MAJOR'
                 then duration_minutes else 0 end)            as major_stoppage_min,
        sum(total_biscuits_made)                              as total_biscuits_made,
        sum(good_biscuits_made)                               as good_biscuits_made
    from events
    group by 1, 2, 3
    -- HAVING: chi giu nhom co Planned Production Time > 0. Co 9 nhom
    -- (may, san pham, ngay) chi toan su kien NO — theo cong thuc moi thi
    -- planned = 0, Availability = NULL, khong do duoc OEE trong ngay do
    -- (giu lai se tao OEE = 0 gia, gay nhieu xu the theo ngay).
    having sum(case when oee_status_group <> 'NO_ORDER' then duration_minutes else 0 end) > 0
)

select
    a.machine,
    a.product,
    a.event_date,
    a.planned_time_min,
    a.downtime_min,
    a.planned_time_min - a.downtime_min                       as run_time_min,
    a.changeover_time_min,
    a.pm_downtime_min,
    a.minor_stoppage_min,
    a.major_stoppage_min,
    a.total_biscuits_made,
    a.good_biscuits_made,
    ts.target_biscuits_per_hour,
    -- Availability = Run Time (suy ra: planned - CC - PM) / Planned Time
    (a.planned_time_min - a.downtime_min)
        / nullif(a.planned_time_min, 0)                       as availability,
    -- Performance = (san luong thuc te / gio chay) / target, CLIP tai 100%
    -- (counter IoT nhieu co the cho ty le > 100%)
    least(
        (a.total_biscuits_made / nullif(a.planned_time_min - a.downtime_min, 0) * 60)
        / nullif(ts.target_biscuits_per_hour, 0),
        1.0
    )                                                          as performance,
    -- Quality = Good / Total, CLIP tai 100%
    least(
        a.good_biscuits_made::numeric / nullif(a.total_biscuits_made, 0),
        1.0
    )                                                          as quality
from aggregated a
left join {{ ref('stg_target_speeds') }} ts
    on a.machine = ts.machine
    and a.product = ts.product
