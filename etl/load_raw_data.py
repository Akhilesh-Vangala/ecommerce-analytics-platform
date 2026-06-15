"""Load raw Olist CSV files into the `raw` schema of `olist_analytics`.

Idempotent: re-running drops and recreates the raw tables (per
sql/ddl/01_raw_schema.sql), then bulk-loads each CSV via COPY, then verifies
row counts against the source files.

Usage:
    .venv/bin/python etl/load_raw_data.py
"""
from __future__ import annotations

import csv
import logging
import sys
import time
from pathlib import Path

from db import get_psycopg2_connection

PROJECT_ROOT = Path(__file__).resolve().parents[1]
DDL_FILE = PROJECT_ROOT / "sql" / "ddl" / "01_raw_schema.sql"
RAW_DATA_DIR = PROJECT_ROOT / "data" / "raw"

# CSV filename -> target table (within `raw` schema)
CSV_TABLE_MAP = {
    "olist_orders_dataset.csv": "raw.orders",
    "olist_order_items_dataset.csv": "raw.order_items",
    "olist_order_payments_dataset.csv": "raw.order_payments",
    "olist_order_reviews_dataset.csv": "raw.order_reviews",
    "olist_customers_dataset.csv": "raw.customers",
    "olist_products_dataset.csv": "raw.products",
    "olist_sellers_dataset.csv": "raw.sellers",
    "olist_geolocation_dataset.csv": "raw.geolocation",
    "product_category_name_translation.csv": "raw.product_category_translation",
}

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger("load_raw_data")


def count_csv_rows(path: Path) -> int:
    with open(path, "r", encoding="utf-8-sig", newline="") as f:
        reader = csv.reader(f)
        next(reader)  # header
        return sum(1 for _ in reader)


def run_ddl(conn) -> None:
    log.info("Applying raw schema DDL: %s", DDL_FILE.relative_to(PROJECT_ROOT))
    with open(DDL_FILE, "r") as f:
        ddl = f.read()
    with conn.cursor() as cur:
        cur.execute(ddl)
    conn.commit()


def load_csv(conn, csv_name: str, table: str) -> tuple[int, int]:
    csv_path = RAW_DATA_DIR / csv_name
    if not csv_path.exists():
        raise FileNotFoundError(
            f"{csv_path} not found - run etl/download_data.py first"
        )

    source_rows = count_csv_rows(csv_path)

    with conn.cursor() as cur:
        with open(csv_path, "r", encoding="utf-8-sig", newline="") as f:
            cur.copy_expert(
                f"COPY {table} FROM STDIN WITH (FORMAT csv, HEADER true, NULL '')",
                f,
            )
        cur.execute(f"SELECT COUNT(*) FROM {table}")
        loaded_rows = cur.fetchone()[0]
    conn.commit()
    return source_rows, loaded_rows


def main() -> int:
    start = time.time()
    conn = get_psycopg2_connection()
    try:
        run_ddl(conn)

        all_ok = True
        log.info("%-45s %12s %12s %6s", "table", "source_rows", "loaded_rows", "match")
        log.info("-" * 80)
        for csv_name, table in CSV_TABLE_MAP.items():
            t0 = time.time()
            source_rows, loaded_rows = load_csv(conn, csv_name, table)
            ok = source_rows == loaded_rows
            all_ok &= ok
            log.info(
                "%-45s %12d %12d %6s  (%.2fs)",
                table,
                source_rows,
                loaded_rows,
                "OK" if ok else "MISMATCH",
                time.time() - t0,
            )

        log.info("-" * 80)
        log.info(
            "Raw load complete in %.2fs - %s",
            time.time() - start,
            "ALL ROW COUNTS MATCH" if all_ok else "ROW COUNT MISMATCH DETECTED",
        )
        return 0 if all_ok else 1
    finally:
        conn.close()


if __name__ == "__main__":
    sys.exit(main())
