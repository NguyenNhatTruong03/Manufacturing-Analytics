-- Staging: 1-1 voi raw.raw_machine — chi trim + cast.
with source as (
    select * from {{ source('raw', 'raw_machine') }}
)

select
    trim(machine_name)  as machine_name,
    trim(machine_type)  as machine_type
from source
