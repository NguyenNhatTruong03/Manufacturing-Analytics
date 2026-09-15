-- Staging: 1-1 voi raw.raw_target_speeds — chi trim + cast.
with source as (
    select * from {{ source('raw', 'raw_target_speeds') }}
)

select
    trim(machine)                          as machine,
    trim(product)                          as product,
    target_biscuits_per_hour::numeric      as target_biscuits_per_hour
from source
