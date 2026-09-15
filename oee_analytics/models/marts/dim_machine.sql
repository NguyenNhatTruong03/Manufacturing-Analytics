-- MART: dim_machine — 1 dong = 1 may (10 may).
select
    {{ dbt_utils.generate_surrogate_key(['machine_name']) }} as machine_key,
    machine_name,
    machine_type
from {{ ref('stg_machine') }}
