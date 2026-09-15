import logging
import sys
from pathlib import Path

import pandas as pd
from sqlalchemy import create_engine, text

# ------------------------------------------------------------------ config
PROJECT_DIR = Path(__file__).resolve().parent.parent  # "Manufacturing Analytics"
EXCEL_PATH = PROJECT_DIR / "data" / "raw_data" / "OEE Manufacturing Report.xlsx"

PG_HOST, PG_PORT, PG_USER, PG_PASSWORD, PG_DATABASE = (
    "localhost", "5432", "postgres", "postgres", "oee_analytics",
)
RAW_SCHEMA = "raw"

SHEET_TABLES = {
    "Fact": "raw_fact",
    "Target Speeds": "raw_target_speeds",
    "Product": "raw_product",
    "Machine": "raw_machine",
}

# So dong ky vong theo plan
EXPECTED_ROWS = {"Fact": 8044}

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)-7s | %(message)s",
    handlers=[logging.StreamHandler(sys.stdout),
              logging.FileHandler(PROJECT_DIR / "oee_analytics" / "extract_load.log",
                                  mode="a", encoding="utf-8")],
)
log = logging.getLogger("extract_load")

# Ten cot -> snake_case, lowercase, chi giu chu/dau gach duoi
def normalize_col(c: str) -> str:
    return (
        str(c).strip().lower()
        .replace(" ", "_").replace("(", "_").replace(")", "_")
        .replace("/", "_").replace("-", "_")
    )


def prepare(df: pd.DataFrame, sheet: str) -> tuple[pd.DataFrame, list[str]]:
    """Tien xu ky thuat: doi ten cot, ep datetime, lo cot loi. KHONG transform nghiep vu."""
    df = df.copy()
    dropped = []

    if sheet == "Fact":
        df["StartDateTime"] = pd.to_datetime(df["StartDateTime"])
        df["EndDateTime"] = pd.to_datetime(df["EndDateTime"])

    if sheet == "Product":
        typo_col = [c for c in df.columns if c.strip().lower().startswith("bsicuits")]
        if typo_col:
            dropped.append(typo_col[0])
            log.warning("Sheet Product: lo cot loi chinh ta '%s' (giu lai 'Biscuits_PER_PALLET')",
                        typo_col[0])
            df = df.drop(columns=typo_col)

    df.columns = [normalize_col(c) for c in df.columns]
    return df, dropped


def main() -> int:
    if not EXCEL_PATH.exists():
        log.error("Khong tim thay file Excel: %s", EXCEL_PATH)
        return 1

    log.info("Doc file: %s", EXCEL_PATH)
    engine = create_engine(
        f"postgresql+psycopg2://{PG_USER}:{PG_PASSWORD}@{PG_HOST}:{PG_PORT}/{PG_DATABASE}"
    )

    with engine.begin() as conn:
        conn.execute(text(f'CREATE SCHEMA IF NOT EXISTS "{RAW_SCHEMA}"'))

    summary = {}
    for sheet, table in SHEET_TABLES.items():
        df = pd.read_excel(EXCEL_PATH, sheet_name=sheet, engine="openpyxl")
        rows_read = len(df)
        df, dropped_cols = prepare(df, sheet)

        with engine.begin() as conn:
            exists = conn.execute(text(
                "SELECT 1 FROM information_schema.tables "
                "WHERE table_schema=:s AND table_name=:t"),
                {"s": RAW_SCHEMA, "t": table}).fetchone()
            if exists:
                conn.execute(text(f'TRUNCATE TABLE "{RAW_SCHEMA}"."{table}"'))
        df.to_sql(table, engine, schema=RAW_SCHEMA, if_exists="append", index=False)

        # doi chieu so dong ky vong
        expected = EXPECTED_ROWS.get(sheet)
        match = "OK" if expected is None else ("OK" if rows_read == expected else "LECH!")
        summary[sheet] = (table, rows_read, dropped_cols, match)
        log.info("Sheet %-14s -> raw.%-18s | %5d dong | cot bi lo: %s | doi chieu plan: %s%s",
                 f"'{sheet}'", table, rows_read, dropped_cols or "khong", match,
                 f"" if expected is None else f" (ky vong {expected})")

    log.info("---- TOM TAT LOAD ----")
    for sheet, (table, n, dropped, match) in summary.items():
        log.info("%-16s %5d dong -> %s.%s [%s]", sheet, n, RAW_SCHEMA, table, match)

    with engine.connect() as conn:
        for table, _ in SHEET_TABLES.items():
            pass
        for sheet, table in SHEET_TABLES.items():
            n = conn.execute(text(f'SELECT COUNT(*) FROM "{RAW_SCHEMA}"."{table}"')).scalar()
            log.info("VERIFY %s.%-18s = %d dong", RAW_SCHEMA, table, n)
    return 0


if __name__ == "__main__":
    sys.exit(main())
