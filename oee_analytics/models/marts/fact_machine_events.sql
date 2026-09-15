-- MART: fact_machine_events — grain: 1 dong = 1 su kien trang thai may
-- (8,044 dong, giong het sheet Fact goc, da clean).
-- cac dong is_duration_outlier / is_unknown_category van duoc GIU LAI de
-- truy vet chat luong du lieu, chi bi loai khoi cac tong thoi gian o
-- fact_oee_daily.
with events as (
    select * from {{ ref('int_events_classified') }}
)

-- GHI CHU LECH PLAN (co ghi trong docs): plan de surrogate key =
-- generate_surrogate_key([machine, start_datetime, product]), nhung du lieu
-- thuc te co 72 cap event trung (machine, start_datetime, product) voi
-- EndDateTime/Duration khac nhau (sensor phat 2 record cung moc start).
-- De giu grain "1 dong = 1 su kien" va khong mat du lieu, key duoc mo rong
-- them end_datetime.
select
    {{ dbt_utils.generate_surrogate_key(['machine', 'start_datetime', 'end_datetime', 'product']) }} as event_id,
    m.machine_key,
    p.product_key,
    e.start_datetime::date as date_key,
    e.machine,
    e.product,
    e.start_datetime,
    e.end_datetime,
    e.duration_minutes,
    e.oee_category_raw,
    e.oee_status_group,
    e.stoppage_class,
    e.total_biscuits_made,
    e.good_biscuits_made,
    e.is_duration_outlier,
    e.is_unknown_category
from events e
left join {{ ref('dim_machine') }} m
    on e.machine = m.machine_name
left join {{ ref('dim_product') }} p
    on e.product = p.product_name
