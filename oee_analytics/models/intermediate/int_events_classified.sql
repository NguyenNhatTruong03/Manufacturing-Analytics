-- INTERMEDIATE: phan loai tung su kien may.
-- Grain: 1 dong = 1 su kien (giu nguyen grain cua stg_fact_events).
--
-- ASSUMPTIONS / DATA CLEANING (ghi ro, khong xu ly am tham):
-- 1. 12 dong co OEE Category = '0' (rac) -> oee_status_group = 'UNKNOWN',
--    gan co is_unknown_category = true. Theo Muc 4 cua plan: cac dong nay
--    duoc log/danh dau de bao cao chat luong du lieu.
-- 2. 17 dong Duration > 1440 phut (max ~35,332 phut ~ 24.5 ngay) -> gan co
    -- is_duration_outlier = true. Gia dinh da duyet theo plan: cac dong nay
--    bi LOAI KHOI cac tong thoi gian (Planned/Downtime/Run) vi tat ca 17 dong
--    deu la NO/CC va khong co san luong; van giu trong fact_machine_events
--    de truy vet.
-- 3. stoppage_class: ap dung cho non-RUN theo dung dinh nghia de bai:
--    MINOR neu duration < 3 phut, MAJOR neu >= 3 phut.
-- 4. PHAN LOAI (ban chinh sua 2026-09-15 theo chi thi cua nguoi duyet):
--    NO (No Order) tach thanh nhom rieng NO_ORDER — Schedule Loss theo
--    Lean OEE, bi LOAI KHOI mau so Planned Production Time va KHONG cong
--    vao Downtime. PM tach thanh PLANNED_DOWNTIME_PM rieng de cong thuc
--    downtime = CHANGEOVER + PLANNED_DOWNTIME_PM ro rang.
with events as (
    select * from {{ ref('stg_fact_events') }}
),

grouped as (
    select
        *,
        case
            when oee_category_raw ilike 'run time%'  then 'RUN'
            when oee_category_raw ilike 'cc%'        then 'CHANGEOVER'
            when oee_category_raw ilike 'pm%'        then 'PLANNED_DOWNTIME_PM'
            when oee_category_raw ilike 'no%'        then 'NO_ORDER'
            else 'UNKNOWN'
        end as oee_status_group,
        (duration_minutes > 1440)                       as is_duration_outlier,
        (oee_category_raw is null or oee_category_raw in ('0', '')) as is_unknown_category
    from events
)

select
    *,
    case
        when oee_status_group <> 'RUN' and duration_minutes < 3  then 'MINOR'
        when oee_status_group <> 'RUN' and duration_minutes >= 3 then 'MAJOR'
        else null
    end as stoppage_class
from grouped
