-- MART: dim_product — 1 dong = 1 dong san pham (18 san pham).
select
    {{ dbt_utils.generate_surrogate_key(['product_name']) }} as product_key,
    product_name,
    biscuits_per_pack,
    biscuits_per_case,
    biscuits_per_pallet
from {{ ref('stg_product') }}
