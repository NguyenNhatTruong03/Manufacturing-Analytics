-- INTERMEDIATE: aggregate theo grain (Machine, Product, Ngay) — co so cho
-- fact_oee_daily. Day la muc aggregate duy nhat ma so dem san luong IoT
-- (TotalBiscuitsMade / GoodMadeBiscuits) duoc coi la on dinh de dung:
-- o record le co 4,116/8,044 dong Good > Total (counter nhieu), nen tuyet
-- doi khong tinh Quality o muc dong le (theo Muc 0 + Muc 4 cua plan).
--
-- ASSUMPTION: cac dong is_duration_outlier bi loai khoi TAT CA cac tong
-- thoi gian (planned/run/changeover/pm/stoppage) de cac thanh phan cong
-- dung lai dung bang planned_time_min; 17 dong nay khong co san luong.
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
        sum(duration_minutes)                                                            as planned_time_min,
        sum(case when oee_status_group = 'RUN'        then duration_minutes else 0 end)  as run_time_min,
        sum(case when oee_status_group = 'CHANGEOVER' then duration_minutes else 0 end)  as changeover_time_min,
        sum(case when oee_status_group = 'PLANNED_DOWNTIME' and oee_category_raw ilike 'pm%'
                                                      then duration_minutes else 0 end)  as pm_downtime_min,
        sum(case when stoppage_class = 'MINOR'        then duration_minutes else 0 end)  as minor_stoppage_min,
        sum(case when stoppage_class = 'MAJOR'        then duration_minutes else 0 end)  as major_stoppage_min,
        sum(total_biscuits_made)                                                         as total_biscuits_made,
        sum(good_biscuits_made)                                                          as good_biscuits_made
    from events
    group by 1, 2, 3
)

select
    a.*,
    ts.target_biscuits_per_hour,
    -- Availability = Run Time / Planned Time
    a.run_time_min / nullif(a.planned_time_min, 0)                                  as availability,
    -- Performance = (san luong thuc te / gio chay) / target, CLIP tai 100%
    -- (counter IoT nhieu co the cho ty le > 100%)
    least(
        (a.total_biscuits_made / nullif(a.run_time_min, 0) * 60)
        / nullif(ts.target_biscuits_per_hour, 0),
        1.0
    )                                                                               as performance,
    -- Quality = Good / Total, CLIP tai 100%
    least(
        a.good_biscuits_made::numeric / nullif(a.total_biscuits_made, 0),
        1.0
    )                                                                               as quality
from aggregated a
left join {{ ref('stg_target_speeds') }} ts
    on a.machine = ts.machine
    and a.product = ts.product
