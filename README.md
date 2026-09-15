# OEE Manufacturing Analytics — Grandma Edna's Biscuits

Pipeline phân tích dữ liệu end-to-end đo lường **OEE (Overall Equipment Effectiveness)** cho nhà máy sản xuất bánh quy Grandma Edna's Biscuits, dựa trên dữ liệu cảm biến IoT tháng 07/2021: **8.044 sự kiện, 10 máy, 18 sản phẩm, 4 bảng (Fact, Target Speeds, Product, Machine)**.


---

## 🏗 Kiến trúc tổng thể

```
[Excel: OEE_Manufacturing_Report.xlsx — 4 sheet]
        │  Python (pandas + openpyxl + SQLAlchemy)  — extract_load.py
        ▼
[PostgreSQL — schema "raw"]          raw_fact (8.044), raw_target_speeds (72),
        │                            raw_product (18), raw_machine (10)
        │                            load thô, idempotent (TRUNCATE + INSERT)
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

**Nguyên tắc:** mọi tính toán OEE nằm trong dbt SQL. Kiến trúc chuẩn medallion (raw ~ Bronze, staging/intermediate ~ Silver, marts ~ Gold).

---

## 📦 Giai đoạn A — Extract & Load

Script `oee_analytics/extract_load.py`:

- Đọc 4 sheet bằng pandas/openpyxl; đổi tên cột về snake_case, ép kiểu datetime, loại cột lỗi chính tả `Bsicuits Per Pallet` của sheet Product (có log WARNING).
- Nạp vào schema `raw` bằng SQLAlchemy + psycopg2 với **TRUNCATE + INSERT**

| Sheet | Bảng raw | Số dòng |
|---|---|---|
| Fact | raw_fact | 8.044 |
| Target Speeds | raw_target_speeds | 72 |
| Product | raw_product | 18 |
| Machine | raw_machine | 10 |

---

## 🧮 Công thức OEE (phiên bản hiện hành)

Tính trong `fact_oee_daily`, grain **1 dòng = Machine + Product + Ngày**:

```
planned_time_min = SUM(duration) WHERE is_duration_outlier = false
                   AND oee_category_raw != 'NO (No Order)'
                   → NO là Schedule Loss theo Lean OEE: không có lệnh sản
                     xuất thì không mất Availability — loại khỏi mẫu số,
                     KHÔNG cộng vào Downtime

downtime_min     = SUM(duration) WHERE nhóm CHANGEOVER (CC)
                   hoặc PLANNED_DOWNTIME_PM (PM), không outlier

run_time_min     = planned_time_min - downtime_min
                   → Run Time được SUY RA (mọi thời gian không phải NO/CC/PM
                     đều coi là đang chạy), KHÔNG dùng literal category
                     = 'Run Time' — lý do xem Phụ lục A.1

availability     = run_time_min / planned_time_min
performance      = (total_biscuits_made / (run_time_min/60))
                   / target_biscuits_per_hour     — clip tại 100%
quality          = good_biscuits_made / total_biscuits_made — clip tại 100%
oee              = availability × performance × quality
```

### Quy tắc làm sạch dữ liệu (đều nằm trong dbt, có test, có ghi docs)

| # | Vấn đề dữ liệu | Xử lý |
|---|---|---|
| 1 | 10/10 tên máy có khoảng trắng thừa → join fail | `TRIM()` mọi cột string ở staging |
| 2 | 12 dòng `OEE Category = 0` (rác) | Nhóm `UNKNOWN` + cờ `is_unknown_category` |
| 3 | 17 dòng `Duration > 1440 phút` (max ~24,5 ngày) | Cờ `is_duration_outlier`, **loại khỏi mọi SUM thời gian**, vẫn giữ ở `fact_machine_events` để truy vết |
| 4 | 51% dòng có `Good > Total` (counter IoT nhiễu) | Chỉ tin sản lượng sau khi SUM theo (máy, sản phẩm, ngày); clip Quality/Performance ở 100% bằng `LEAST` |
| 5 | 3 cặp sự kiện bị sensor ghi 2 lần (trùng cả khung thời gian) | Dedup ở staging, 8.044 → 8.041 dòng |
| 6 | 9 nhóm ngày chỉ toàn NO → planned = 0 | Loại khỏi `fact_oee_daily` (HAVING planned > 0), 179 → 170 dòng |
| 7 | Cột lỗi chính tả sheet Product | Loại ngay lúc load Python (có log) |

---

## 🔨 Giai đoạn B — dbt 3 tầng

**13 models** (materialization: staging → view, intermediate → view, marts → table):

| Tầng | Model | Vai trò |
|---|---|---|
| staging | `stg_fact_events` | rename/cast/trim/dedup sheet Fact |
| staging | `stg_target_speeds` | trim + cast target speed |
| staging | `stg_product` | chuẩn hoá quy cách đóng gói (đã bỏ cột lỗi chính tả) |
| staging | `stg_machine` | trim danh mục máy |
| intermediate | `int_events_classified` | phân loại `oee_status_group` (RUN / CHANGEOVER / PLANNED_DOWNTIME_PM / NO_ORDER / UNKNOWN), `stoppage_class` (MINOR < 3 phút, MAJOR ≥ 3 phút), cờ outlier |
| intermediate | `int_daily_machine_product` | aggregate theo (máy, sản phẩm, ngày), áp công thức planned/downtime/run ở trên, tính A/P/Q |
| marts | `dim_machine`, `dim_product`, `dim_date` | Star Schema dimensions; `dim_date` có day_of_week, is_weekend phục vụ phân tích xu hướng |
| marts | `fact_machine_events` | 8.041 dòng sự kiện cấp máy, surrogate key = (machine, start, end, product) |
| marts | `fact_oee_daily` | 170 dòng, bảng lõi OEE |
| marts | `mart_oee_monthly_summary` | OEE toàn nhà máy theo tháng (weighted theo tổng) |
| marts | `mart_whatif_pm_reduction` | Kịch bản giảm 15% PM downtime |

**Kiểm thử:** `dbt build` → **PASS 85/85** (13 models + 72 data tests): `not_null`, `unique` (surrogate key mọi bảng mart), `accepted_values` (5 nhóm `oee_status_group`, `stoppage_class`), `relationships` (3 FK machine/product/date), custom `dbt_utils.expression_is_true` cho `availability/performance/quality/oee ≤ 1`, `accepted_range` cho duration/target. dbt docs sinh tại `target/index.html`; mọi giả định ghi trong `schema.yml`.

---

## 📊 Giai đoạn C — Dashboard (Metabase)

Metabase chạy local `http://localhost:3000` (đăng nhập `admin@oee.local / OeeDashboard2026!`), collection **OEE Analytics**, kết nối trực tiếp schema `marts`. Toàn bộ 5 trang + 22 cards được dựng **tự động bằng REST API** (`build_metabase_dashboard.py`, idempotent — chạy lại sẽ xoá và tạo lại các cards/dashboard có tiền tố `[OEE]`).

| Trang | Nội dung chính | Câu hỏi trả lời (file word) |
|---|---|---|
| 1 · Tổng quan nhà máy | KPI OEE/A/P/Q, gap vs World Class 85%, xu hướng OEE theo ngày, OEE theo thứ trong tuần (cuối tuần vs ngày thường) | #1, #8 |
| 2 · Phân tích máy (Bottleneck) | Máy OEE thấp nhất, OEE theo máy + **tooltip lý do dừng khi hover**, breakdown A/P/Q, bảng ổn định (OEE TB + độ lệch chuẩn) | #2, #9 |
| 3 · Downtime & Changeover | Tổng giờ dừng, giờ dừng theo trạng thái, Minor vs Major, % CC, CC theo máy | #3, #4, #7 |
| 4 · Chất lượng & Product | Waste % theo sản phẩm, performance gap máy+sản phẩm so Target Speeds, tốc độ thực tế vs target theo máy | #5, #6 |
| 5 · What-if PM (−15%) | Bảng + biểu đồ giờ chạy thêm và sản lượng làm thêm theo máy | #10 |

- **Filter chung mọi trang:** khoảng ngày / machine / product (dashboard-level parameters).
- **Advanced tooltip:** biểu đồ "OEE theo máy" có cột *Lý do dừng chính* hiện top-3 trạng thái tốn thời gian nhất khi hover.
- **Drill-through:** click điểm ngày trên biểu đồ xu hướng Trang 1 → mở Trang 2 với filter ngày đó.

---

## 📈 Kết quả số liệu (tháng 07/2021, công thức hiện hành)

| Chỉ số toàn nhà máy | Giá trị |
|---|---|
| Planned Production Time (đã loại NO) | 31.101 phút ≈ 518,3 giờ |
| Run Time (suy ra) | 8.191 phút ≈ 136,5 giờ |
| Downtime (CC + PM) | 22.910 phút ≈ 381,8 giờ (CC 378,3h + PM 3,5h) |
| **Availability** | **26,34%** |
| **Performance** | **100%** (bị clip tại trần do counter nhiễu) |
| **Quality** | **34,89%** |
| **OEE** | **9,19%** (World Class ≥ 85%) |
| NO (No Order) — Schedule Loss | 1.104 giờ, nằm ngoài mẫu số |
| CC / tổng downtime | 99,1% |
| Minor vs Major stoppage | Minor 83,1h vs Major 1.439,7h — Major áp đảo |
| Waste % cao nhất | Vienesse Creams, Peanut Cookies, Orange Creams (~33,3%) |

Theo máy: chỉ **Biscuit Filling Machine** có Run Time (136,5h, A = 42,3%); 9 máy còn lại availability = 0% vì toàn bộ thời gian có đơn hàng của chúng đều mang nhãn CC — xem **Phụ lục A.3** để hiểu vì sao đây có thể là vấn đề gán nhãn dữ liệu chứ chưa chắc là thực tế vận hành.

---

## 🚀 Chạy lại từ đầu

Yêu cầu: Python 3.12+, PostgreSQL local, dbt-postgres, Java 17/21 (Metabase).

```bash
# 0. Cài dependency Python
pip install pandas openpyxl sqlalchemy psycopg2-binary dbt-postgres requests

# 1. Tạo database
psql -U postgres -c "CREATE DATABASE oee_analytics"

# 2. Extract & Load 
python oee_analytics/extract_load.py

# 3. dbt build
cd oee_analytics
dbt deps --profiles-dir .
dbt build --profiles-dir .
dbt docs generate --profiles-dir .

# 4. Metabase + dashboard
java -jar metabase.jar 
python build_metabase_dashboard.py
```

## 📁 Cấu trúc repo

```
oee_analytics/
├── extract_load.py               # Giai đoạn A
├── dbt_project.yml / profiles.yml / packages.yml
├── macros/generate_schema_name.sql
├── models/
│   ├── staging/                  # 4 model + sources.yml + models.yml
│   ├── intermediate/             # 2 model + models.yml
│   └── marts/                    # 7 model + models.yml
├── build_metabase_dashboard.py   # Giai đoạn C (Metabase REST API)
└── target/index.html             # dbt docs
data/raw_data/                    # Đề bài.docx + OEE Manufacturing Report.xlsx
```
---

## 📎 PHỤ LỤC A — Vì sao các số liệu cũ không còn chính xác (dữ liệu sai như thế nào)

Các phiên bản trình bày trước ngày 15/09/2026 dùng công thức cũ và cho ra **Availability ≈ 0,25%, OEE ≈ 0,09–0,15%**. Các con số đó **không phản ánh đúng vận hành** vì 2 lỗi định nghĩa sau:

### A.1 Dùng literal nhãn `'Run Time'` làm tử số Availability
Trong 8.044 dòng, nhãn `Run Time` chỉ xuất hiện **9 dòng (~240 phút, tập trung ở 1/10 máy)** — cảm biến gần như không bao giờ gán nhãn này dù máy đang sản xuất (counter bánh vẫn chạy suốt). Lấy đúng nhãn đó làm Run Time khiến tử số Availability gần bằng 0 → OEE toàn nhà máy sụp về ~0,1%.
**Đã sửa:** Run Time = Planned Time − (CC + PM); mọi thời gian không phải NO/CC/PM đều được coi là đang chạy.

### A.2 Cộng `NO (No Order)` vào mẫu số Planned Time
Công thức cũ tính Planned Time = mọi sự kiện trong ngày, kể cả NO (~2.295 giờ). NO là **Schedule Loss theo Lean OEE** — không có đơn hàng thì không tính là mất Availability; để NO trong mẫu số kéo Availability xuống thấp thêm.
**Đã sửa:** NO bị loại hoàn toàn khỏi Planned Time và không cộng vào Downtime (3.996 dòng NO vẫn giữ nguyên ở `fact_machine_events` để truy vết).

Sau khi sửa: Availability 0,25% → **26,34%**, OEE → **9,19%** — hợp lý hơn về mặt vận hành, tuy vẫn thấp hơn xa chuẩn World Class 85%.

### A.3 Số liệu hiện hành vẫn phải đọc kèm cảnh báo dữ liệu
- **CC chiếm 378,3h / 518,3h = 73% Planned Time** và 99,1% tổng downtime → 9/10 máy có availability = 0%. Bằng chứng gán nhãn đáng ngờ: 1.841/1.977 dòng CC của Biscuit Filling và 816/1.071 dòng CC của Biscuit Sprinkling **kèm counter sản lượng** (~540 triệu và ~120 triệu bánh được đếm trong lúc ghi "vệ sinh thay khuôn") — dấu hiệu cảm biến đếm bánh liên tục bất kể nhãn trạng thái, hoặc nhãn CC bị dùng như trạng thái mặc định. Ngược lại, 8 máy còn lại có dòng CC không kèm counter nào.
- **Performance = 100% nằm ở trần clip** vì counter nhiễu (51% dòng có Good > Total) — Performance thực không đo được tin cậy từ dữ liệu này.
- **Kết luận:** OEE = 9,19% là kết quả của công thức đã duyệt trên dữ liệu hiện có; khuyến nghị kinh doanh (ưu tiên đầu tư máy nào) nên chờ IT xác minh việc gán nhãn trạng thái cảm biến. Toàn bộ giả định được ghi trong dbt docs (`schema.yml` của `fact_oee_daily`).
