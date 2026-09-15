# OEE Manufacturing Analytics — Grandma Edna's Biscuits

Pipeline phân tích dữ liệu end-to-end đo lường **OEE (Overall Equipment Effectiveness)** cho nhà máy sản xuất bánh quy Grandma Edna's Biscuits, dựa trên dữ liệu cảm biến IoT của tháng 07/2021 (10 máy, 18 sản phẩm, 8.044 sự kiện).

---

## 🏗 Kiến trúc tổng thể

```
[Excel: OEE_Manufacturing_Report.xlsx — 4 sheet]
        │  Python (pandas + openpyxl + SQLAlchemy)  — extract_load.py
        ▼
[PostgreSQL — schema "raw"]          raw_fact (8.044), raw_target_speeds (72),
        │                            raw_product (18), raw_machine (10) — load thô, idempotent
        │  dbt Core (postgres adapter)
        ▼
STAGING       (views)   → clean, rename, cast, TRIM, dedup
        ▼
INTERMEDIATE  (views)   → phân loại trạng thái, cờ outlier, aggregate theo ngày
        ▼
MARTS         (tables)  → Star Schema: dim_machine, dim_product, dim_date,
        │                  fact_machine_events, fact_oee_daily,
        │                  mart_oee_monthly_summary, mart_whatif_pm_reduction
        ▼
[Metabase] — 5 trang dashboard, filter ngày/machine/product,
             tooltip lý do dừng máy, drill-through Trang 1 → Trang 2
```

**Nguyên tắc:** tầng Python không chứa business logic — mọi tính toán OEE nằm trong dbt SQL.

## 🧮 Công thức OEE (tính trong `fact_oee_daily`, grain Machine + Product + Ngày)

| Chỉ số | Công thức |
|---|---|
| Availability | `run_time_min / planned_time_min` |
| Performance | `(total_biscuits_made / (run_time_min/60)) / target_biscuits_per_hour` — clip 100% |
| Quality | `good_biscuits_made / total_biscuits_made` — clip 100% |
| OEE | `Availability × Performance × Quality` |

Xử lý dữ liệu nhiễu (chi tiết trong `models/*/​*.yml` — dbt docs):
- **TRIM** toàn bộ string trước khi join (tên máy gốc có space thừa).
- 12 dòng `OEE Category = 0` (rác) → nhóm `UNKNOWN`, gắn cờ `is_unknown_category`.
- 17 dòng `Duration > 1440 phút` (max ~35.332 phút) → gắn cờ `is_duration_outlier`, loại khỏi tổng Planned Time, giữ lại để truy vết.
- Counter IoT nhiễu (4.116/8.044 dòng có `Good > Total`) → chỉ tin sản lượng ở mức **SUM theo (máy, sản phẩm, ngày)**, clip Quality/Performance ở 100% bằng `LEAST`.
- Sheet Product: cột lỗi chính tả `Bsicuits Per Pallet` bị loại ngay lúc load (có log), giữ `biscuits_per_pallet`.

## 📁 Cấu trúc repo

```
oee_analytics/
├── extract_load.py               # Giai đoạn A: Excel → schema raw (TRUNCATE+INSERT, idempotent)
├── dbt_project.yml               # Giai đoạn B: cấu hình dbt
├── profiles.yml                  # Kết nối Postgres (đổi password trước khi dùng!)
├── packages.yml                  # dbt_utils
├── macros/generate_schema_name.sql
├── models/
│   ├── staging/                  # stg_fact_events, stg_target_speeds, stg_product, stg_machine
│   ├── intermediate/             # int_events_classified, int_daily_machine_product
│   └── marts/                    # dim_*, fact_*, mart_oee_monthly_summary, mart_whatif_pm_reduction
├── build_metabase_dashboard.py   # Giai đoạn C: dựng 5 dashboard qua Metabase REST API
├── metabase.jar                  # Metabase (tải riêng — xem hướng dẫn bên dưới)
└── target/index.html             # dbt docs
data/raw_data/                    # Đề bài.docx + OEE Manufacturing Report.xlsx (input)

```

## 🚀 Chạy dự án

Yêu cầu: Python 3.12+, PostgreSQL (local), dbt-postgres, Java 17/21 (cho Metabase).

```bash
# 0. Cài dependency Python
pip install pandas openpyxl sqlalchemy psycopg2-binary dbt-postgres requests

# 1. Tạo database
psql -U postgres -c "CREATE DATABASE oee_analytics"

# 2. Giai đoạn A — Extract & Load
python oee_analytics/extract_load.py

# 3. Giai đoạn B — dbt build
cd oee_analytics
dbt deps --profiles-dir .
dbt build --profiles-dir .        # PASS 84/84
dbt docs generate --profiles-dir .

# 4. Giai đoạn C — chạy Metabase dựng dashboard
java -jar metabase.jar            # http://localhost:3000 healthy
python build_metabase_dashboard.py   # tự setup admin, kết nối schema marts, tạo 5 dashboard
```

Kết quả dashboard (Metabase local, collection **OEE Analytics**):

| Trang | Nội dung | Câu hỏi được trả lời |
|---|---|---|
| 1 · Tổng quan nhà máy | KPI OEE/A/P/Q, gap vs World Class 85%, xu hướng theo ngày, ngày trong tuần | #1, #8 |
| 2 · Phân tích máy (Bottleneck) | OEE theo máy + tooltip lý do dừng, breakdown A/P/Q, độ ổn định (stddev) | #2, #9 |
| 3 · Downtime & Changeover | Downtime theo trạng thái, Minor vs Major, % CC, CC theo máy | #3, #4, #7 |
| 4 · Chất lượng & Product | Waste % theo sản phẩm, Performance gap vs Target Speeds | #5, #6 |
| 5 · What-if PM (−15%) | Giờ chạy thêm & sản lượng thêm nếu giảm 15% PM downtime | #10 |

Mỗi trang có 3 filter dashboard-level: **khoảng ngày / machine / product**. Drill-through: click điểm ngày ở biểu đồ xu hướng Trang 1 → Trang 2 với filter ngày đó.

## 📊 Số liệu thực tế sau khi triển khai (tháng 07/2021)

- Planned Time: 97.363 phút | Run Time: 240 phút | Downtime: 97.123 phút
- Availability ≈ 0,23% | Performance = 100% (đã clip) | Quality ≈ 80,4% → **OEE ≈ 0,15%**
- Downtime lớn nhất: NO (No Order) ~2.295h, CC ~561h; PM chỉ ~3,5h → what-if −15% PM gần như 0.

