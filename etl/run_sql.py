"""Generic SQL file runner against olist_analytics.

Executes a .sql file as a single transaction and commits. Used to apply
staging/marts transformations and data-quality check scripts.

Usage:
    .venv/bin/python etl/run_sql.py sql/staging/01_staging_transform.sql
"""
from __future__ import annotations

import logging
import sys
import time
from pathlib import Path

from db import get_psycopg2_connection

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger("run_sql")


def main(sql_path: str) -> int:
    path = Path(sql_path)
    if not path.exists():
        log.error("File not found: %s", path)
        return 1

    sql = path.read_text()
    conn = get_psycopg2_connection()
    t0 = time.time()
    try:
        with conn.cursor() as cur:
            cur.execute(sql)
        conn.commit()
        log.info("Applied %s in %.2fs", path, time.time() - t0)
        return 0
    except Exception:
        conn.rollback()
        log.exception("Failed applying %s", path)
        return 1
    finally:
        conn.close()


if __name__ == "__main__":
    if len(sys.argv) != 2:
        print("usage: run_sql.py <path/to/file.sql>")
        sys.exit(1)
    sys.exit(main(sys.argv[1]))
