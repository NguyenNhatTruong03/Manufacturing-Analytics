-- Staging: 1-1 voi raw.raw_product — chi trim + cast.
-- Cot loi chinh ta "Bsicuits Per Pallet" da bi loai o buoc load (Python),
-- o day chi con 1 cot pallet duy nhat: biscuits_per_pallet.
with source as (
    select * from {{ source('raw', 'raw_product') }}
)

select
    trim(product_name)          as product_name,
    biscuits_per_pack::int      as biscuits_per_pack,
    biscuits_per_case::int      as biscuits_per_case,
    biscuits_per_pallet::int    as biscuits_per_pallet
from source
