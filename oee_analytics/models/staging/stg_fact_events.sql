-- Staging: 1-1 voi raw.raw_fact — chi rename / cast / trim / dedup, khong co business logic.
-- DEDUP (theo Muc 1 plan: staging co "dedup"): co 3 cap event bi cam bien
-- ghi 2 lan — trung (machine, start_datetime, end_datetime, product) va trung
-- Duration, chi khac gia tri counter (IoT chup 2 lan). Giu 1 dong moi cap,
-- 8,044 -> 8,041 dong (da ghi trong docs, khong xu ly am tham).
with source as (
    select * from {{ source('raw', 'raw_fact') }}
),

trimmed as (
    select
        trim(machine)               as machine,
        startdatetime::timestamp    as start_datetime,
        enddatetime::timestamp      as end_datetime,
        duration::numeric           as duration_minutes,
        totalbiscuitsmade::bigint   as total_biscuits_made,
        goodmadebiscuits::bigint    as good_biscuits_made,
        trim(oee_category)          as oee_category_raw,
        trim(product)               as product
    from source
),

deduplicated as (
    select
        *,
        row_number() over (
            partition by machine, start_datetime, end_datetime, product
            order by total_biscuits_made desc
        ) as rn
    from trimmed
)

select
    machine,
    start_datetime,
    end_datetime,
    duration_minutes,
    total_biscuits_made,
    good_biscuits_made,
    oee_category_raw,
    product
from deduplicated
where rn = 1
