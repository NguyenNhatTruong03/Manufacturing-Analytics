# -*- coding: utf-8 -*-
import time
import uuid

import requests

BASE = "http://localhost:3000"
PG = {"host": "localhost", "port": 5432, "dbname": "oee_analytics",
      "user": "-----", "password": "-----"}
ADMIN = {"first_name": "OEE", "last_name": "Analyst",
         "email": "------", "password": "-------",
         "site_name": "OEE Grandma Edna's Biscuits"}

DB_NAME = "OEE Marts (Postgres)"
COLLECTION = "OEE Analytics"


class MB:
    def __init__(self):
        self.s = requests.Session()
        self.token = None

    def wait_health(self, timeout=300):
        print("Dang cho Metabase khoi dong")
        t0 = time.time()
        while time.time() - t0 < timeout:
            try:
                r = self.s.get(f"{BASE}/api/health", timeout=3)
                if r.ok and r.json().get("status") == "ok":
                    print("Metabase da san sang.")
                    return
            except Exception:
                pass
            time.sleep(5)
        raise RuntimeError("Metabase khong khoi dong dung han.")

    def setup(self):
        props = self.s.get(f"{BASE}/api/session/properties").json()
        token = props.get("setup-token")
        if not token:
            print("Da setup truoc do — dang nhap.")
        else:
            r = self.s.post(f"{BASE}/api/setup", json={
                "token": token, "user": ADMIN,
                "prefs": {"site_name": ADMIN["site_name"],
                          "site_locale": "en", "allow_tracking": False}})
            r.raise_for_status()
            print("Setup xong: " + ADMIN["email"])
        r = self.s.post(f"{BASE}/api/session",
                        json={"username": ADMIN["email"],
                              "password": ADMIN["password"]})
        r.raise_for_status()
        self.token = r.json()["id"]

    def get(self, path, **kw):
        r = self.s.get(f"{BASE}{path}", headers=self._h(), timeout=60, **kw)
        r.raise_for_status()
        return r.json() if r.text else None

    def post(self, path, data=None):
        r = self.s.post(f"{BASE}{path}", headers=self._h(), json=data, timeout=120)
        if not r.ok:
            raise RuntimeError(f"POST {path} -> {r.status_code}: {r.text[:500]}")
        return r.json() if r.text else None

    def put(self, path, data=None):
        r = self.s.put(f"{BASE}{path}", headers=self._h(), json=data, timeout=120)
        if not r.ok:
            raise RuntimeError(f"PUT {path} -> {r.status_code}: {r.text[:500]}")
        return r.json() if r.text else None

    def _h(self):
        h = {"Content-Type": "application/json"}
        if self.token:
            h["X-Metabase-Session"] = self.token
        return h


def main():
    mb = MB()
    mb.wait_health()
    mb.setup()

    dbs = mb.get("/api/database")["data"]
    db = next((d for d in dbs if d["name"] == DB_NAME), None)
    if not db:
        db = mb.post("/api/database", {
            "engine": "postgres", "name": DB_NAME,
            "details": dict(PG, sslmode="disable"), "is_full_sync": True})
        print(f"Da tao database connection #{db['id']}")
    db_id = db["id"]

    for _ in range(60):
        info = mb.get(f"/api/database/{db_id}")
        if info.get("initial_sync_status") == "complete":
            break
        time.sleep(5)
    print("Sync schema marts xong.")

    meta = mb.get(f"/api/database/{db_id}/metadata")
    fields = {}
    for t in meta["tables"]:
        for f in t["fields"]:
            fields[(t["name"], f["name"])] = f["id"]

    def fid(table, col):
        return fields[(table, col)]

    for c in mb.get("/api/card?f=all") or []:
        if c["name"].startswith("[OEE] "):
            requests.delete(f"{BASE}/api/card/{c['id']}", headers=mb._h())
    for d in mb.get("/api/dashboard?f=all") or []:
        if d["name"].startswith("[OEE] "):
            requests.delete(f"{BASE}/api/dashboard/{d['id']}", headers=mb._h())

    collection = next((c for c in mb.get("/api/collection") if c["name"] == COLLECTION), None)
    if not collection:
        collection = mb.post("/api/collection", {"name": COLLECTION})
    coll_id = collection["id"]

    # ================= CARD DEFINITIONS =================
    def ftags(table, need_date=True, need_machine=True, need_product=True):
        tags = {}
        if need_date:
            tags["date_range"] = {
                "id": str(uuid.uuid4()), "name": "date_range",
                "display-name": "Khoảng ngày", "type": "dimension",
                "widget-type": "date/range",
                "dimension": ["field", fid(table, "date_key"), None]}
        if need_machine:
            tags["machine"] = {
                "id": str(uuid.uuid4()), "name": "machine",
                "display-name": "Machine", "type": "dimension",
                "widget-type": "string/=",
                "dimension": ["field", fid(table, "machine"), None]}
        if need_product:
            tags["product"] = {
                "id": str(uuid.uuid4()), "name": "product",
                "display-name": "Product", "type": "dimension",
                "widget-type": "string/=",
                "dimension": ["field", fid(table, "product"), None]}
        return tags

    def tag_sql(table, need_date=True, need_machine=True, need_product=True):
        parts = []
        if need_date:
            parts.append("[[AND {{date_range}}]]")
        if need_machine:
            parts.append("[[AND {{machine}}]]")
        if need_product:
            parts.append("[[AND {{product}}]]")
        return ("WHERE 1=1 " + " ".join(parts)) if parts else ""

    cards = []  # (key, payload)

    def add_card(key, name, sql, display, viz=None, tags=None):
        payload = {
            "name": f"[OEE] {name}",
            "display": display,
            "visualization_settings": viz or {},
            "dataset_query": {"database": db_id, "type": "native",
                              "native": {"query": sql,
                                         "template-tags": tags or {}}},
            "collection_id": coll_id,
        }
        cards.append((key, payload))

    FOD, FME, WIF = "fact_oee_daily", "fact_machine_events", "mart_whatif_pm_reduction"

    # ---------- PAGE 1: Tong quan (#1, #8) ----------
    t = ftags(FOD)
    add_card("kpi_oee", "P1 · OEE trung bình (%)",
             f'SELECT round(100.0*avg(oee),2) AS "OEE %" FROM marts.{FOD} {tag_sql(FOD)}',
             "scalar", {"global": {"title": False}}, t)
    for col, label in [("availability", "Availability"), ("performance", "Performance"),
                       ("quality", "Quality")]:
        add_card(f"kpi_{col}", f"P1 · {label} trung bình (%)",
                 f'SELECT round(100.0*avg({col}),2) AS "{label} %" FROM marts.{FOD} {tag_sql(FOD)}',
                 "scalar", {}, t)
    add_card("kpi_worldclass", "P1 · So với World Class 85% (gap điểm %)",
             f'SELECT round(100.0*avg(oee) - 85.0, 2) AS "Gap vs 85% (điểm)" FROM marts.{FOD} {tag_sql(FOD)}',
             "scalar", {}, t)
    add_card("oee_trend", "P2 · Xu hướng OEE theo ngày",
             f'SELECT date_key AS "Ngày", round(100.0*avg(oee),2) AS "OEE %" '
             f'FROM marts.{FOD} {tag_sql(FOD)} GROUP BY 1 ORDER BY 1',
             "line", {"graph.dimensions": ["Ngày"], "graph.metrics": ["OEE %"]}, t)
    add_card("oee_dow", "P3 · OEE theo ngày trong tuần (cuối tuần vs ngày thường)",
             f'SELECT day_name AS "Thứ", CASE WHEN is_weekend THEN \'Cuối tuần\' ELSE \'Ngày thường\' END AS "Nhóm", '
             f'round(100.0*avg(oee),2) AS "OEE %" '
             f'FROM marts.{FOD} {tag_sql(FOD)} GROUP BY 1,2 '
             f'ORDER BY min(date_key)',
             "bar", {"graph.dimensions": ["Thứ", "Nhóm"], "graph.metrics": ["OEE %"]}, t)

    # ---------- PAGE 2: Phan tich may (#2, #9) ----------
    t = ftags(FOD)
    add_card("oee_machine", "P1 · OEE theo máy (tooltip: lý do dừng chính)",
             f'SELECT x."Máy", x."OEE %", r."Lý do dừng chính (tooltip)" '
             f'FROM (SELECT machine AS "Máy", round(100.0*avg(oee),2) AS "OEE %" '
             f'FROM marts.{FOD} d {tag_sql(FOD)} GROUP BY machine) x '
             f'CROSS JOIN LATERAL (SELECT string_agg(s.r, \' · \') AS "Lý do dừng chính (tooltip)" FROM ('
             f'SELECT e.oee_category_raw || \': \' || round(sum(e.duration_minutes)/60.0,1) || \'h\' AS r '
             f'FROM marts.{FME} e WHERE e.machine = x."Máy" AND e.oee_status_group <> \'RUN\' '
             f'GROUP BY e.oee_category_raw ORDER BY sum(e.duration_minutes) DESC LIMIT 3) s) r '
             f'ORDER BY x."OEE %" ASC',
             "bar", {"graph.dimensions": ["Máy"], "graph.metrics": ["OEE %"]}, t)
    add_card("apq_machine", "P2 · Breakdown Availability / Performance / Quality theo máy",
             f'SELECT machine AS "Máy", round(100.0*avg(availability),1) AS "Availability %", '
             f'round(100.0*avg(performance),1) AS "Performance %", round(100.0*avg(quality),1) AS "Quality %" '
             f'FROM marts.{FOD} {tag_sql(FOD)} GROUP BY 1 ORDER BY 4 DESC',
             "bar", {"graph.dimensions": ["Máy"],
                     "graph.metrics": ["Availability %", "Performance %", "Quality %"]}, t)
    add_card("worst_machine", "P1 · Máy có OEE thấp nhất (bottleneck)",
             f'SELECT machine AS "Máy OEE thấp nhất" FROM (SELECT machine, avg(oee) o '
             f'FROM marts.{FOD} {tag_sql(FOD)} GROUP BY 1) x ORDER BY o ASC LIMIT 1',
             "scalar", {}, t)
    add_card("stability", "P3 · Máy ổn định & cao nhất (OEE trung bình + độ lệch chuẩn)",
             f'SELECT machine AS "Máy", round(100.0*avg(oee),2) AS "OEE TB %", '
             f'round(100.0*stddev_samp(oee),2) AS "Độ lệch chuẩn (càng thấp càng ổn định)", '
             f'round(100.0*avg(availability),1) AS "A %", round(100.0*avg(performance),1) AS "P %", '
             f'round(100.0*avg(quality),1) AS "Q %" '
             f'FROM marts.{FOD} {tag_sql(FOD)} GROUP BY 1 ORDER BY "OEE TB %" DESC',
             "table", {}, t)

    # ---------- PAGE 3: Downtime & Changeover (#3, #4, #7) ----------
    t = ftags(FME)
    add_card("total_downtime", "P1 · Tổng thời gian dừng máy (giờ)",
             f'SELECT round(sum(downtime_min)/60.0,1) AS "Giờ dừng máy" '
             f'FROM marts.{FOD} {tag_sql(FOD)}', "scalar", {}, ftags(FOD))
    add_card("downtime_cat", "P2 · Thời gian dừng theo trạng thái (giờ)",
             f'SELECT oee_category_raw AS "Trạng thái", round(sum(duration_minutes)/60.0,1) AS "Giờ" '
             f'FROM marts.{FME} WHERE oee_status_group <> \'RUN\' AND 1=1 '
             f'[[AND {{{{date_range}}}}]] [[AND {{{{machine}}}}]] [[AND {{{{product}}}}]] '
             f'GROUP BY 1 ORDER BY 2 DESC',
             "bar", {"graph.dimensions": ["Trạng thái"], "graph.metrics": ["Giờ"]}, t)
    add_card("minor_major", "P2 · Minor (<3 phút) vs Major (>=3 phút) stoppage (giờ)",
             f'SELECT stoppage_class AS "Loại sự cố", round(sum(duration_minutes)/60.0,1) AS "Giờ" '
             f'FROM marts.{FME} WHERE stoppage_class IS NOT NULL AND 1=1 '
             f'[[AND {{{{date_range}}}}]] [[AND {{{{machine}}}}]] [[AND {{{{product}}}}]] '
             f'GROUP BY 1 ORDER BY 2 DESC',
             "bar", {"graph.dimensions": ["Loại sự cố"], "graph.metrics": ["Giờ"]}, t)
    t7 = ftags(FOD, need_product=False)
    add_card("cc_pct", "P1 · CC chiếm % tổng downtime",
             f'SELECT round(100.0*sum(changeover_time_min)/nullif(sum(downtime_min),0),1) AS "CC % downtime" '
             f'FROM marts.{FOD} {tag_sql(FOD, need_product=False)}', "scalar", {}, t7)
    add_card("cc_machine", "P2 · Thời gian Changeover (CC) theo máy (giờ)",
             f'SELECT machine AS "Máy", round(sum(changeover_time_min)/60.0,1) AS "Giờ CC" '
             f'FROM marts.{FOD} {tag_sql(FOD, need_product=False)} GROUP BY 1 ORDER BY 2 DESC',
             "bar", {"graph.dimensions": ["Máy"], "graph.metrics": ["Giờ CC"]}, t7)

    # ---------- PAGE 4: Chat luong & Product (#5, #6) ----------
    t = ftags(FOD)
    add_card("waste_product", "P1 · Waste % theo sản phẩm (1 - Quality)",
             f'SELECT product AS "Sản phẩm", round(100.0*(1-avg(quality)),2) AS "Waste %" '
             f'FROM marts.{FOD} {tag_sql(FOD)} GROUP BY 1 ORDER BY 2 DESC',
             "bar", {"graph.dimensions": ["Sản phẩm"], "graph.metrics": ["Waste %"]}, t)
    add_card("perf_gap", "P2 · Performance gap so với Target Speeds (máy + sản phẩm)",
             f'SELECT machine AS "Máy", product AS "Sản phẩm", '
             f'round(max(target_biscuits_per_hour),0) AS "Target (bánh/giờ)", '
             f'round(sum(total_biscuits_made)/nullif(sum(run_time_min)/60.0,0),0) AS "Thực tế (bánh/giờ)", '
             f'round(100.0*avg(performance),1) AS "Performance %" '
             f'FROM marts.{FOD} {tag_sql(FOD)} GROUP BY 1,2 ORDER BY "Performance %" ASC LIMIT 20',
             "table", {}, t)
    add_card("speed_machine", "P3 · Tốc độ thực tế vs Target theo máy",
             f'SELECT machine AS "Máy", '
             f'round(sum(total_biscuits_made)/nullif(sum(run_time_min)/60.0,0),0) AS "Thực tế (bánh/giờ)", '
             f'round(sum(coalesce(target_biscuits_per_hour,0)*run_time_min/60.0)/nullif(sum(run_time_min)/60.0,0),0) AS "Target (bánh/giờ)" '
             f'FROM marts.{FOD} {tag_sql(FOD)} GROUP BY 1 ORDER BY 2 ASC',
             "bar", {"graph.dimensions": ["Máy"],
                     "graph.metrics": ["Thực tế (bánh/giờ)", "Target (bánh/giờ)"]}, t)

    # ---------- PAGE 5: What-if PM (#10) ----------
    t5 = ftags(WIF, need_date=False, need_product=False)
    sql5 = tag_sql(WIF, need_date=False, need_product=False)
    add_card("whatif_table", "P1 · Kịch bản giảm 15% PM downtime theo máy",
             f'SELECT machine AS "Máy", round(pm_downtime_min/60.0,1) AS "PM hiện tại (giờ)", '
             f'round(pm_downtime_reduced_min/60.0,2) AS "Giảm 15% (giờ)", '
             f'round(extra_run_hours,2) AS "Giờ chạy thêm", '
             f'round(extra_products_estimated,0) AS "Sản phẩm làm thêm (ước tính)" '
             f'FROM marts.{WIF} {sql5} ORDER BY "Giờ chạy thêm" DESC',
             "table", {}, t5)
    add_card("whatif_hours", "P2 · Giờ chạy thêm nếu giảm 15% PM (theo máy)",
             f'SELECT machine AS "Máy", round(extra_run_hours,2) AS "Giờ chạy thêm" '
             f'FROM marts.{WIF} {sql5} ORDER BY 2 DESC',
             "bar", {"graph.dimensions": ["Máy"], "graph.metrics": ["Giờ chạy thêm"]}, t5)
    add_card("whatif_products", "P2 · Sản phẩm làm thêm nếu giảm 15% PM (theo máy)",
             f'SELECT machine AS "Máy", round(extra_products_estimated,0) AS "Sản phẩm thêm" '
             f'FROM marts.{WIF} {sql5} ORDER BY 2 DESC',
             "bar", {"graph.dimensions": ["Máy"], "graph.metrics": ["Sản phẩm thêm"]}, t5)

    # ---- tao cards ----
    card_ids = {}
    for key, payload in cards:
        c = mb.post("/api/card", payload)
        card_ids[key] = c["id"]
    print(f"Da tao {len(card_ids)} cards.")

    # ================= DASHBOARDS =================
    PARAMS = [
        {"id": "p_date", "name": "Khoảng ngày", "slug": "date_range", "type": "date/range"},
        {"id": "p_machine", "name": "Machine", "slug": "machine", "type": "string/="},
        {"id": "p_product", "name": "Product", "slug": "product", "type": "string/="},
    ]

    def pm(card_key, need_date=True, need_machine=True, need_product=True):
        maps = []
        if need_date:
            maps.append({"parameter_id": "p_date", "card_id": card_ids[card_key],
                         "target": ["dimension", ["template-tag", "date_range"]]})
        if need_machine:
            maps.append({"parameter_id": "p_machine", "card_id": card_ids[card_key],
                         "target": ["dimension", ["template-tag", "machine"]]})
        if need_product:
            maps.append({"parameter_id": "p_product", "card_id": card_ids[card_key],
                         "target": ["dimension", ["template-tag", "product"]]})
        return maps

    def dc(card_key, row, col, sx, sy, mappings):
        return {"id": -abs(hash(card_key)) % 100000, "card_id": card_ids[card_key],
                "row": row, "col": col, "size_x": sx, "size_y": sy,
                "parameter_mappings": mappings, "visualization_settings": {}}

    dashboards = {}

    def make_dash(name, dashcards, desc=""):
        d = mb.post("/api/dashboard", {"name": f"[OEE] {name}", "description": desc,
                                       "collection_id": coll_id, "parameters": PARAMS})
        mb.put(f"/api/dashboard/{d['id']}", {"dashcards": dashcards})
        dashboards[name] = d["id"]
        print(f"Dashboard '{name}' (#{d['id']}) — {len(dashcards)} cards.")
        return d["id"]

    # Trang 1
    make_dash("Trang 1 · Tổng quan nhà máy", [
        dc("kpi_oee", 0, 0, 5, 4, pm("kpi_oee")),
        dc("kpi_availability", 0, 5, 5, 4, pm("kpi_availability")),
        dc("kpi_performance", 0, 10, 5, 4, pm("kpi_performance")),
        dc("kpi_quality", 0, 15, 4, 4, pm("kpi_quality")),
        dc("kpi_worldclass", 0, 19, 5, 4, pm("kpi_worldclass")),
        dc("oee_trend", 4, 0, 14, 8, pm("oee_trend", need_machine=False, need_product=False)),
        dc("oee_dow", 4, 14, 10, 8, pm("oee_dow", need_machine=False, need_product=False)),
    ], "Q1: OEE thang 07/2021 vs World Class 85% | Q8: xu the theo ngay trong tuan. Drill-through: click vao diem bieu do xu the de sang Trang 2.")

    # Trang 2 (+ click-through tu trang 1 da lam o trend)
    d2 = make_dash("Trang 2 · Phân tích máy (Bottleneck)", [
        dc("worst_machine", 0, 0, 8, 4, pm("worst_machine")),
        dc("oee_machine", 0, 8, 16, 8, pm("oee_machine")),
        dc("apq_machine", 4, 0, 8, 6, pm("apq_machine")),
        dc("stability", 8, 0, 24, 8, pm("stability")),
    ], "Q2: may OEE thap nhat + nguyen nhan (tooltip ly do dung) | Q9: may on dinh nhat (stddev).")


    # Trang 2 (chi tiet may) voi filter khoang ngay = ngay duoc click.
    try:
        dash1_id = dashboards["Trang 1 · Tổng quan nhà máy"]
        dash1 = mb.get(f"/api/dashboard/{dash1_id}")
        dashcards = dash1["dashcards"]
        changed = False
        for dcard in dashcards:
            if dcard.get("card_id") == card_ids["oee_trend"]:
                vs = dict(dcard.get("visualization_settings") or {})
                vs["click_behavior"] = {
                    "type": "link", "linkType": "dashboard",
                    "targetId": dashboards["Trang 2 · Phân tích máy (Bottleneck)"],
                    "parameterMapping": {"p_date": {
                        "id": "p_date",
                        "source": {"type": "column", "id": "Ngày", "name": "Ngày"},
                        "target": {"type": "parameter", "id": "p_date"}}}}
                dcard["visualization_settings"] = vs
                changed = True
        if changed:
            clean = [{"id": c["id"], "card_id": c.get("card_id"), "row": c["row"],
                      "col": c["col"], "size_x": c["size_x"], "size_y": c["size_y"],
                      "parameter_mappings": c.get("parameter_mappings") or [],
                      "visualization_settings": c.get("visualization_settings") or {}}
                     for c in dashcards]
            mb.put(f"/api/dashboard/{dash1_id}", {"dashcards": clean})
            print("Drill-through Trang 1 -> Trang 2 (click diem Ngay) da gan.")
    except Exception as e:
        print("Bo qua drill-through setup:", e)

    # Trang 3
    make_dash("Trang 3 · Downtime & Changeover", [
        dc("total_downtime", 0, 0, 8, 4, pm("total_downtime", need_product=False)),
        dc("cc_pct", 0, 8, 8, 4, pm("cc_pct", need_product=False)),
        dc("downtime_cat", 0, 16, 8, 8, pm("downtime_cat", need_product=False)),
        dc("minor_major", 4, 0, 8, 6, pm("minor_major", need_product=False)),
        dc("cc_machine", 4, 8, 8, 6, pm("cc_machine", need_product=False)),
    ], "Q3: tong thoi gian dung + trang thai ton nhieu nhat | Q4: Minor vs Major | Q7: % CC va may ton CC nhieu nhat.")

    # Trang 4
    make_dash("Trang 4 · Chất lượng & Product", [
        dc("waste_product", 0, 0, 12, 8, pm("waste_product", need_machine=False)),
        dc("speed_machine", 0, 12, 12, 8, pm("speed_machine", need_product=False)),
        dc("perf_gap", 8, 0, 24, 10, pm("perf_gap")),
    ], "Q5: san pham Waste % cao nhat | Q6: may/san pham khong dat target speed.")

    # Trang 5
    make_dash("Trang 5 · What-if PM (-15%)", [
        dc("whatif_hours", 0, 0, 12, 8, pm("whatif_hours", need_date=False, need_product=False)),
        dc("whatif_products", 0, 12, 12, 8, pm("whatif_products", need_date=False, need_product=False)),
        dc("whatif_table", 8, 0, 24, 10, pm("whatif_table", need_date=False, need_product=False)),
    ], "Q10: giam 15% PM downtime -> them bao nhieu gio chay & san pham.")

    print("\n=== HOAN TAT ===")
    for name, did in dashboards.items():
        print(f"  {BASE}/dashboard/{did}  ->  {name}")


if __name__ == "__main__":
    main()
