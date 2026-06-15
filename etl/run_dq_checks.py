"""Run the data-quality check suite and render docs/data_quality_report.md.

Usage:
    .venv/bin/python etl/run_dq_checks.py
Exit code is non-zero if any check has status FAIL.
"""
from __future__ import annotations

import datetime as dt
import logging
import sys
from collections import defaultdict
from pathlib import Path

from db import get_psycopg2_connection

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SQL_FILE = PROJECT_ROOT / "sql" / "data_quality" / "dq_checks.sql"
REPORT_FILE = PROJECT_ROOT / "docs" / "data_quality_report.md"

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger("run_dq_checks")


def main() -> int:
    sql = SQL_FILE.read_text()
    conn = get_psycopg2_connection()
    try:
        with conn.cursor() as cur:
            cur.execute(sql)
            rows = cur.fetchall()
    finally:
        conn.close()

    by_category: dict[str, list[tuple]] = defaultdict(list)
    n_pass = n_fail = n_info = 0
    for category, check_name, status, detail, description in rows:
        by_category[category].append((check_name, status, detail, description))
        if status == "PASS":
            n_pass += 1
        elif status == "FAIL":
            n_fail += 1
        else:
            n_info += 1

    lines = []
    lines.append("# Data Quality Report")
    lines.append("")
    lines.append(f"_Generated: {dt.datetime.now().isoformat(timespec='seconds')}_")
    lines.append("")
    lines.append(
        f"**Summary: {n_pass} PASS / {n_fail} FAIL / {n_info} INFO "
        f"out of {len(rows)} checks**"
    )
    lines.append("")
    if n_fail:
        lines.append("> :warning: One or more checks FAILED - see below.")
    else:
        lines.append("> All assertion checks passed. INFO rows document known, handled data realities.")
    lines.append("")

    for category, checks in by_category.items():
        lines.append(f"## {category}")
        lines.append("")
        lines.append("| Check | Status | Detail | Description |")
        lines.append("|---|---|---|---|")
        for check_name, status, detail, description in checks:
            badge = {"PASS": "PASS", "FAIL": "**FAIL**", "INFO": "INFO"}[status]
            lines.append(f"| {check_name} | {badge} | {detail} | {description} |")
        lines.append("")

    REPORT_FILE.parent.mkdir(parents=True, exist_ok=True)
    REPORT_FILE.write_text("\n".join(lines))
    log.info("Wrote %s (%d PASS / %d FAIL / %d INFO)", REPORT_FILE.relative_to(PROJECT_ROOT), n_pass, n_fail, n_info)

    return 1 if n_fail else 0


if __name__ == "__main__":
    sys.exit(main())
