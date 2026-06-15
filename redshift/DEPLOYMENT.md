# Redshift Deployment Guide

This project is built and runs end-to-end on **local PostgreSQL 16**. Every SQL file in
`sql/` is written in ANSI/Redshift-compatible SQL on purpose (see
`docs/sql_query_catalog.md` §0.2), and the marts DDL (`sql/marts/01_dims.sql`,
`sql/marts/02_facts.sql`) carries inline `-- Redshift: ...` comments documenting the
`DISTSTYLE`/`DISTKEY`/`SORTKEY` choices that would be used in production.

This document is the **"full Redshift DDL variant"** those comments point to: a concrete,
step-by-step runbook for standing up the same warehouse on Amazon Redshift, plus a list of
the handful of places where local-Postgres SQL needs to change to run on Redshift.

> **You do not need to do any of this to use the project.** Everything (warehouse, 27
> analytics queries, 6 notebooks, dashboard extracts) already runs against local Postgres.
> This doc exists to (a) demonstrate cloud-deployment awareness for interviews, and (b) be
> a ready-to-execute runbook if you do want to stand up a real Redshift cluster.

---

## 1. Provisioning

For a dataset this size (~1.5 GB raw, ~113K order-item rows, ~100K orders), a full
multi-node provisioned cluster is overkill. Two options, cheapest first:

| Option | When to use | Notes |
|---|---|---|
| **Redshift Serverless** (recommended) | Demoing, interview take-homes, short-lived analysis | Pay per RPU-second; create a workgroup + namespace, run your session, then delete/pause the workgroup. No cluster sizing decisions. |
| **Provisioned `dc2.large`, 1 node** | If Serverless isn't available in your account/region | Smallest provisioned node type; still ~$0.25/hr (us-east-1, on-demand) — remember to delete the cluster when done. |

Either way you end up with: an **endpoint hostname**, **port** (default `5439`), a
**database name**, and **admin credentials** — these map directly onto the `REDSHIFT_*`
variables already stubbed in `.env.example`.

---

## 2. Connection setup

`etl/db.py` reads `DB_HOST` / `DB_PORT` / `DB_NAME` / `DB_USER` / `DB_PASSWORD` from `.env`
and builds a `postgresql+psycopg2://` SQLAlchemy URL plus a raw `psycopg2` connection.
**Redshift is wire-compatible with PostgreSQL via psycopg2**, so the *same* `get_engine()`
/ `get_psycopg2_connection()` functions work unchanged against a Redshift endpoint — you
only need to point the `DB_*` variables at Redshift instead of local Postgres:

```bash
# .env, pointed at Redshift instead of local Postgres
DB_HOST=<your-workgroup>.<account>.<region>.redshift-serverless.amazonaws.com
DB_PORT=5439
DB_NAME=olist_analytics
DB_USER=admin
DB_PASSWORD=<set a real password - Redshift requires one, unlike local peer auth>
```

The commented-out `REDSHIFT_*` block in `.env.example` is kept as a *side-by-side*
reference (so you can keep local Postgres creds in `DB_*` and Redshift creds documented
separately) — `db.py` itself only ever reads `DB_*`. If you want to run against both
targets without editing `.env` each time, the simplest approach is two `.env` files
(`.env.local`, `.env.redshift`) and pass `--env-file` / set `DOTENV_PATH` before calling
`load_dotenv` — not implemented here to keep `db.py` minimal, but a 2-line change if
needed.

For full Redshift-specific type support (e.g. `SUPER`, `VARBYTE`) you'd swap to the
`sqlalchemy-redshift` dialect (`redshift+psycopg2://`), but none of this project's DDL
uses Redshift-only types, so the plain `postgresql+psycopg2://` URL is sufficient.

---

## 3. Loading raw data: S3 + COPY instead of row-by-row INSERT

`etl/load_raw_data.py` loads the 9 source CSVs via pandas `.to_sql()` (row-by-row
INSERTs through psycopg2) — fine for ~1.5GB locally, but **the wrong pattern for
Redshift**, where bulk loads should always go through `COPY` from S3 (orders of magnitude
faster, and avoids saturating the leader node with INSERT statements).

**Migration steps:**

1. Upload the raw CSVs to an S3 bucket: `aws s3 cp data/raw/ s3://<your-bucket>/olist/raw/ --recursive`
2. Create an IAM role with `s3:GetObject` on that bucket, attach it to the Redshift
   cluster/workgroup (Redshift console → "Manage IAM roles").
3. Run `sql/ddl/01_raw_schema.sql` against Redshift unchanged (it's plain `CREATE TABLE`
   statements with standard types — no incompatibilities).
4. Replace each `load_raw_data.py` INSERT step with a `COPY`, e.g.:

```sql
COPY raw.olist_orders_dataset
FROM 's3://<your-bucket>/olist/raw/olist_orders_dataset.csv'
IAM_ROLE 'arn:aws:iam::<account-id>:role/<your-redshift-role>'
CSV
IGNOREHEADER 1
DATEFORMAT 'auto'
TIMEFORMAT 'auto';
```

Repeat for all 9 raw tables (8 Olist datasets + `product_category_name_translation`).
Everything downstream (`sql/staging/`, `sql/marts/`) is plain `CREATE TABLE AS SELECT`
and runs identically once the raw tables are populated.

---

## 4. Marts DDL: applying DISTSTYLE / DISTKEY / SORTKEY

Redshift's `CREATE TABLE ... AS SELECT` (CTAS) accepts distribution/sort attributes
directly in the table header — the SELECT body does **not** change at all. The pattern is:

```sql
CREATE TABLE <schema>.<table>
[ DISTSTYLE { ALL | EVEN | KEY } ] [ DISTKEY (<column>) ]
[ [COMPOUND] SORTKEY (<column> [, ...]) ]
AS
<the exact SELECT already in sql/marts/01_dims.sql or 02_facts.sql>;
```

### 4.1 Consolidated attribute reference (all 8 mart tables)

| Table | DISTSTYLE | DISTKEY | SORTKEY | Source |
|---|---|---|---|---|
| `dim_date` | ALL | — | `date_day` | `01_dims.sql` |
| `dim_customer` | ALL | — | `customer_unique_id` | `01_dims.sql` |
| `dim_product` | ALL | — | `product_id` | `01_dims.sql` |
| `dim_seller` | ALL | — | `seller_id` | `01_dims.sql` |
| `dim_geography` | ALL | — | `zip_code_prefix` | `01_dims.sql` |
| `fact_orders` | KEY | `customer_unique_id` | `order_purchase_date` | `02_facts.sql` |
| `fact_order_items` | KEY | `order_id` | `order_purchase_date` | `02_facts.sql` |
| `fact_order_payments` | KEY | `order_id` | `order_purchase_date` | `02_facts.sql` |

**Rationale** (already documented inline in the source files): all 5 dimensions are small
(<100K rows) so `DISTSTYLE ALL` broadcasts a full copy to every compute node, making every
fact→dim join a local join with zero network shuffle. The 3 fact tables use `DISTKEY` to
co-locate related rows (a customer's orders together; an order's items/payments with that
order) for the joins the analytics catalog actually performs, and `SORTKEY
(order_purchase_date)` because every trend/cohort/window-function query in
`sql/analytics/` filters or orders by purchase date — sort-key pruning (zone maps) turns
those range scans into much smaller block reads.

### 4.2 Worked examples

**`dim_customer`** — header changes from:
```sql
CREATE TABLE marts.dim_customer AS
WITH customer_orders AS ( ... )
```
to:
```sql
CREATE TABLE marts.dim_customer
DISTSTYLE ALL
SORTKEY (customer_unique_id)
AS
WITH customer_orders AS ( ... )
```
— the `WITH ... SELECT ...` body is copy-pasted verbatim from `sql/marts/01_dims.sql`.

**`fact_orders`** — header changes from:
```sql
CREATE TABLE marts.fact_orders AS
WITH item_agg AS ( ... )
```
to:
```sql
CREATE TABLE marts.fact_orders
DISTSTYLE KEY
DISTKEY (customer_unique_id)
SORTKEY (order_purchase_date)
AS
WITH item_agg AS ( ... )
```
— again, the body is unchanged from `sql/marts/02_facts.sql`. The same pattern applies to
`fact_order_items` and `fact_order_payments` (both `DISTKEY (order_id)`).

---

## 5. Known Postgres → Redshift incompatibilities (and fixes)

These are the **only** places in the codebase that would need to change to run on real
Redshift. Everything else (staging CTAS, all 27 analytics queries except where noted, all
window functions — `NTILE`, `RANK`, `LAG`, `ROWS BETWEEN`) is identical on both engines.

### 5.1 `CREATE INDEX` — not supported on Redshift

`sql/marts/02_facts.sql` has several `CREATE INDEX idx_...` statements (e.g.
`idx_fact_orders_purchase_date`). Redshift has **no traditional B-tree indexes** — it
relies entirely on distribution style, sort keys, and zone maps. **Fix**: drop every
`CREATE INDEX` statement; the `SORTKEY (order_purchase_date)` chosen in §4.1 already
covers the most common range-filter pattern those indexes were targeting.

### 5.2 `PRIMARY KEY` / `FOREIGN KEY` constraints — informational only

Redshift accepts `ADD CONSTRAINT ... PRIMARY KEY` / `FOREIGN KEY` syntax (so the
`ALTER TABLE ... ADD PRIMARY KEY` / `ADD CONSTRAINT ... FOREIGN KEY` statements in
`01_dims.sql` / `02_facts.sql` won't error), but **Redshift does not enforce them** — they
exist purely as metadata hints for the query planner's join-cardinality estimates. No
change needed to run, but don't rely on them to catch data-integrity bugs the way you
would in Postgres — that's what `sql/data_quality/dq_checks.sql` is for.

### 5.3 `dim_date`'s `generate_series` — leader-node restriction

`sql/marts/01_dims.sql`'s `dim_date` is built from
`generate_series('2016-01-01'::date, '2018-12-31'::date, '1 day'::interval)`. Redshift
implements `generate_series` as a **leader-node-only** function, and leader-node results
can't always be materialized directly into a compute-node table via CTAS. **Fix**:
generate the 1,096-row date spine in Python (`pandas.date_range`), write it to a small CSV,
and `COPY` it in — a standard, well-documented pattern for Redshift date dimensions. The
column derivations (`year`, `quarter`, `month_name`, `iso_week`, `is_weekend`, etc.) are
trivial to reproduce with `pandas` (`.dt.year`, `.dt.quarter`, `.dt.day_name()`, ...).

### 5.4 `(ARRAY_AGG(...) ORDER BY ...)[1]` — Postgres array-indexing, not Redshift SQL

`sql/marts/02_facts.sql`'s `fact_orders.primary_payment_type` is computed as:
```sql
(ARRAY_AGG(payment_type ORDER BY payment_value DESC))[1]
```
This Postgres idiom (aggregate into an array, then index `[1]`) isn't valid Redshift SQL.
**Fix** — replace with a window-function + filter pattern:
```sql
-- in payment_agg CTE, add:
ROW_NUMBER() OVER (PARTITION BY order_id ORDER BY payment_value DESC) AS rn
-- then in the outer SELECT:
MAX(CASE WHEN rn = 1 THEN payment_type END) AS primary_payment_type
```
(or an equivalent `FIRST_VALUE(...) OVER (...)` — either is standard and Redshift-safe).

### 5.5 `PERCENTILE_CONT` — must be a window function (`OVER (...)`) on Redshift

This is the most important fix, because it affects **9 lines across 2 of the 27 cataloged
analytics queries**. In Postgres, `PERCENTILE_CONT(p) WITHIN GROUP (ORDER BY col)` is an
**ordered-set aggregate** — it works directly with `GROUP BY` (or with no `GROUP BY` for a
single overall value), exactly as used in:

- `sql/analytics/02_customer_rfm_cohorts.sql:115` (Q2.2's median days-to-2nd-order)
- `sql/analytics/03_fulfillment_ops.sql:75,76,85,86,95,96,106,107` (Q3.3's median/p90 for
  all 4 cycle-time stages)

**Redshift only supports `PERCENTILE_CONT`/`PERCENTILE_DISC` as window functions** — they
*require* an `OVER (PARTITION BY ...)` clause (an empty `OVER ()` for "whole result set").
**Fix** — append `OVER ()` to each call and adjust the surrounding query to a single row
via `LIMIT 1` (or `DISTINCT`) since a window function repeats the value on every input row
rather than collapsing to one row like an aggregate. Example for Q3.3's approval-hours
median:

```sql
-- Postgres (current, in sql/analytics/03_fulfillment_ops.sql):
SELECT
    COUNT(*) AS n,
    ROUND(PERCENTILE_CONT(0.5) WITHIN GROUP (ORDER BY approval_hours)::numeric, 2) AS median_value
FROM marts.fact_orders
WHERE order_approved_at IS NOT NULL;

-- Redshift-compatible rewrite:
SELECT DISTINCT
    n,
    ROUND(median_value::numeric, 2) AS median_value
FROM (
    SELECT
        COUNT(*) OVER ()                                                          AS n,
        PERCENTILE_CONT(0.5) WITHIN GROUP (ORDER BY approval_hours) OVER ()       AS median_value
    FROM marts.fact_orders
    WHERE order_approved_at IS NOT NULL
) sub;
```

Q3.3's `UNION ALL` of 4 stages and Q2.2's per-cohort median would each need this same
`OVER () + DISTINCT` wrapper. This is a mechanical, well-understood rewrite — flagged here
so it's not a surprise if/when this project is pointed at a real Redshift cluster.

---

## 6. Running the analytics catalog on Redshift

With the §5 fixes applied, all 27 queries in `sql/analytics/` run unchanged on Redshift —
they were written using only the window-function/CTE subset that's portable
(`NTILE`, `RANK`, `LAG`, `ROW_NUMBER`, `SUM/AVG/COUNT(...) OVER (...)`, `ROWS BETWEEN`
frames, `DATE_TRUNC`, `EXTRACT`). The 6 Jupyter notebooks and `etl/export_dashboard_extracts.py`
need no changes at all — they go through `etl/db.py`, which (per §2) works against either
target by changing 5 environment variables.

---

## 7. Cost & cleanup

For Redshift Serverless: delete the workgroup and namespace after your session (data in S3
is untouched, so you can recreate the warehouse later by re-running §3-§4). For a
provisioned cluster: either delete it (and optionally take a final snapshot) or pause it
(`dc2`/`ra3` node types support pause/resume, which stops compute billing while retaining
storage). At this dataset's scale, a full rebuild from S3 takes only a few minutes, so
there's no need to keep a cluster running between sessions.
