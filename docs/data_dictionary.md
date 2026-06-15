# Data Dictionary

**Project:** Olist Brazilian E-Commerce — End-to-End Retail & Fulfillment Analytics
**Scope:** Every column in every table/file produced by this project — the raw layer, staging layer, marts (star schema), and the 24 Tableau dashboard extracts.
**Companion docs:** `PROJECT_PLAN.md` (architecture & scope) · `docs/data_quality_report.md` (39-check DQ framework) · `docs/sql_query_catalog.md` (business question → query → answer) · `docs/dashboard_build_guide.md` (Tableau build spec) · `docs/CASE_STUDY.md` (findings & recommendations).

---

## 0. How to Read This Document

### 0.1 Layered architecture

```
raw  ─▶  staging  ─▶  marts (star schema)  ─▶  dashboard/extracts/*.csv (24)  ─▶  Tableau Public (7 pages)
```

- **raw** (`raw` schema, §1): pass-through of the 9 Olist Kaggle source CSVs, 1 table each, minimal typing. Preserves source fidelity for lineage/debugging.
- **staging** (`staging` schema, §2): 1 model per raw source — type casts, trims/normalizes text, deduplicates, and surfaces `dq_*` data-quality flags. No cross-subject-area joins yet.
- **marts** (`marts` schema, §3): star schema (5 dimensions + 3 facts), analysis-ready. This is the **single source of truth** for every SQL analytics query (`sql/analytics/*.sql`) and the basis for every dashboard extract.
- **dashboard/extracts** (§5): 24 flat, pre-aggregated CSVs consumed directly by the 7-page Tableau Public workbook. All logic is ported from the validated `notebooks/_build_nb0*.py` pipelines (NB1–NB6) — the export script introduces **no new analytical methodology**, so dashboard numbers are guaranteed to reconcile with the notebook narrative and with `marts.*`.

### 0.2 Source dataset

Olist Brazilian E-Commerce Public Dataset (Kaggle). **99,441 orders**, placed between **2016-09-04 and 2018-09-03** (`order_purchase_timestamp` range; per `kpi_summary.csv`). Currency = Brazilian Real (R$ / BRL) — **no FX conversion is applied anywhere** in this project. `dim_date` spans **2016-01-01 to 2018-12-31** (1,096 days) — deliberately wider than the order date range so that timestamp arithmetic and FK joins never fall outside the calendar spine, and so cohort/seasonality windows have buffer on both ends.

### 0.3 "Valid" vs "delivered" vs "reviewed" populations

Most extract files compute metrics over one of these populations, not "all rows." Getting this wrong silently changes every downstream percentage.

| Population | Definition (pandas / SQL) | Excludes | n |
|---|---|---|---|
| **All orders** | every row in `fact_orders` | nothing | 99,441 |
| **Valid orders** | `order_status NOT IN ('canceled','unavailable')` | 625 canceled + 609 unavailable | 98,207 |
| **Delivered orders** | `is_delivered = TRUE AND dq_delivered_missing_date = FALSE` | non-delivered statuses + 8 orders with status='delivered' but no `delivered_customer_date` | 96,470 |
| **Reviewed orders** | `review_score IS NOT NULL` | 768 orders (0.77%) with no matching review row | 98,673 |

Each per-file entry in §5.2 states which of these (or which combination — e.g. "delivered AND reviewed") applies.

### 0.4 Numeric scale conventions — read before building anything in Tableau

| Prefix / pattern | Scale | Tableau format | Example |
|---|---|---|---|
| `pct_*`, `*_pct` (e.g. `pct_late`, `repeat_rate_pct`, `gmv_mom_pct`) | **0–100** (percentage points) | Custom Number Format `0.0\%` | `pct_late = 8.11` means **8.11%** |
| `is_*`, `dq_*`, `has_*` flags | **0/1** (boolean) | n/a as a flag; built-in Percentage format if `AVG()`'d | `is_late = 1` |
| `predicted_*_risk` (Model A/B scores) | **0.0–1.0** (probability) | built-in Percentage format if displayed as a rate | `predicted_late_risk = 0.42` means **42%** |
| `freight_ratio`, `avg_freight_ratio` | **0.0–1.0** (fraction) | built-in Percentage format | `freight_ratio = 0.18` means freight is **18%** of order value |

This split convention is intentional: every `pct_*` field was explicitly multiplied by 100 during export specifically for Tableau readability (see `etl/export_dashboard_extracts.py`), while ratio/probability fields were left as raw 0–1 fractions because they are most often consumed via `AVG()` + Tableau's built-in Percentage format. **Mixing these two up is the single most common Tableau-from-CSV formatting bug** — see `docs/dashboard_build_guide.md` §0.1 for the full discussion (this exact bug was caught and fixed for `pct_late` in `customer_segments.csv` / `segment_profile_summary.csv` during this project's QA pass — both now consistently 0–100 like every other `pct_*` field).

### 0.5 A day-of-week gotcha: two conventions coexist

- `marts.dim_date.day_of_week` (Postgres `EXTRACT(DOW)`): **Sunday = 0 … Saturday = 6**.
- `purchase_dow` in `orders_detail.csv` / `risk_scores_late_delivery.csv`'s feature set (pandas `.dt.dayofweek`, computed directly from `order_purchase_timestamp` in `etl/export_dashboard_extracts.py` — **not** joined from `dim_date`): **Monday = 0 … Sunday = 6**.

The two never appear together in the same file, but if this project is ever extended to join an extract's `purchase_dow` against `dim_date.day_of_week`, one side must be remapped first — they disagree both on which day is "0" and on the rotation direction.

### 0.6 Geography reference tables

**`BR_REGION`** — maps every 2-letter Brazilian state code (incl. Distrito Federal) to one of 5 IBGE macro-regions. Used to derive every `*_region` column.

| Region | States |
|---|---|
| North | AC, AP, AM, PA, RO, RR, TO |
| Northeast | AL, BA, CE, MA, PB, PE, PI, RN, SE |
| Central-West | DF, GO, MT, MS |
| Southeast | ES, MG, RJ, SP |
| South | PR, RS, SC |

**`BR_STATE_NAME`** — every `*_state` (2-letter) column in the extracts is paired with a `*_state_name` (full Portuguese name, e.g. "São Paulo") column purely so Tableau's built-in Brazil geocoding (State/Province geographic role) can render choropleths with no external shapefile/geojson. Full 27-entry mapping lives in `etl/export_dashboard_extracts.py::BR_STATE_NAME`. Note the disambiguation gotcha documented in `docs/dashboard_build_guide.md`: "Distrito Federal" as a state name collides with a Mexican state in Tableau's geocoding, so every data source that uses State/Province roles also carries a `Country = "Brazil"` calculated field.

---

## 1. Raw Layer (`raw` schema)

8 tables, one per source CSV from the Olist Kaggle dataset (`sql/ddl/01_raw_schema.sql`). Loosely-typed, minimal constraints (PK only where the source guarantees uniqueness) — cleaning happens in staging.

| Table | Row count | Grain | Key columns | Notes |
|---|---|---|---|---|
| `raw.orders` | 99,441 | 1 row / order | `order_id`, `customer_id`, `order_status`, 5 lifecycle timestamps (purchase, approved, delivered-to-carrier, delivered-to-customer, estimated-delivery) | Source of every `fact_orders` timing metric |
| `raw.order_items` | 112,650 | 1 row / `(order_id, order_item_id)` | `order_id`, `order_item_id`, `product_id`, `seller_id`, `price`, `freight_value`, `shipping_limit_date` | |
| `raw.order_payments` | 103,886 | 1 row / `(order_id, payment_sequential)` | `order_id`, `payment_sequential`, `payment_type`, `payment_installments`, `payment_value` | Multiple rows per order possible (split / multi-method payments) |
| `raw.order_reviews` | 99,224 | ~1 row / order (not guaranteed) | `review_id`, `order_id`, `review_score` (1–5), `review_comment_title/message`, `review_creation_date`, `review_answer_timestamp` | 547 orders have 2–3 review rows; 789 `review_id`s duplicated — deduplicated in staging |
| `raw.customers` | 99,441 | 1 row / `customer_id` (1:1 with orders) | `customer_id`, `customer_unique_id`, `customer_zip_code_prefix`, `customer_city`, `customer_state` | `customer_unique_id` = the real person; 96,096 distinct values |
| `raw.products` | 32,951 | 1 row / `product_id` | `product_id`, `product_category_name`, dimensions/weight, `product_photos_qty`, name/description length | 610 rows have NULL `product_category_name` |
| `raw.sellers` | 3,095 | 1 row / `seller_id` | `seller_id`, `seller_zip_code_prefix`, `seller_city`, `seller_state` | |
| `raw.geolocation` | ~1,000,000 | many rows / zip prefix | `geolocation_zip_code_prefix`, `geolocation_lat`, `geolocation_lng`, `geolocation_city`, `geolocation_state` | ~19,015 distinct zip prefixes, each with multiple (often inconsistent) city/state pings — deduplicated to centroids in staging |
| `raw.product_category_translation` | 71 | 1 row / category | `product_category_name` (PT), `product_category_name_english` | 2 categories present in `raw.products` are missing from this table — manually mapped in staging (§2) |

---

## 2. Staging Layer (`staging` schema)

7 models (dbt-CTAS style), one per raw source. Type-cast, trim/normalize text, deduplicate, and surface `dq_*` flags. **No cross-subject-area joins** — that happens in marts. Full DDL: `sql/staging/01_staging_transform.sql`.

| Model | Rows | Source → transformation | `dq_*` flags |
|---|---|---|---|
| `stg_orders` | 99,441 | Pass-through of `raw.orders` + `LOWER(TRIM(order_status))` | `dq_delivered_missing_date` — TRUE when `order_status='delivered'` AND `order_delivered_customer_date IS NULL` (8 rows) |
| `stg_customers` | 99,441 | Pass-through of `raw.customers` + `LOWER(TRIM(city))`, `UPPER(TRIM(state))`. Grain = `customer_id` (1 per order's customer record) — `customer_unique_id` is deduplicated to the person level in `dim_customer` | — |
| `stg_sellers` | 3,095 | Pass-through of `raw.sellers` + `LOWER(TRIM(city))`, `UPPER(TRIM(state))` | — |
| `stg_geolocation` | 19,015 | Deduplicates `raw.geolocation` (~1M rows, ~19K distinct zip prefixes) to 1 row per zip: `latitude`/`longitude` = `AVG()` centroid across all pings for that prefix; `city`/`state` = the **most frequently reported** value per prefix (via `ROW_NUMBER() OVER (PARTITION BY zip ORDER BY COUNT(*) DESC)`); `n_pings` = ping count | — |
| `stg_products` | 32,951 | `LEFT JOIN` to `product_category_translation`. `product_category_name_english` = `COALESCE(translation, manual_mapping, 'unknown')` where the 2 manual mappings are `portateis_cozinha_e_preparadores_de_alimentos → kitchen_portables_and_food_prep` and `pc_gamer → pc_gamer`. `product_category_name` itself = `COALESCE(raw_value, 'unknown')`. Adds `product_volume_cm3 = length_cm × height_cm × width_cm` and renames the source's "lenght" typo to `product_name_length` / `product_description_length` | `dq_category_missing` — TRUE when source `product_category_name IS NULL` (610 rows) |
| `stg_order_items` | 112,650 | Pass-through of `raw.order_items` | `dq_negative_amount` — TRUE when `price < 0 OR freight_value < 0` (0 rows) |
| `stg_order_payments` | 103,886 | Pass-through of `raw.order_payments` + `LOWER(TRIM(payment_type))` | `dq_negative_amount` — TRUE when `payment_value < 0` (0 rows) |
| `stg_order_reviews` | 98,673 | Deduplicates `raw.order_reviews` (99,224 rows) to **1 row per `order_id`**, keeping the most recently created review (ties broken by `review_answer_timestamp`, then `review_id`) via `ROW_NUMBER() OVER (PARTITION BY order_id ORDER BY review_creation_date DESC, review_answer_timestamp DESC, review_id)` | `dq_had_multiple_reviews` — TRUE for the 547 orders that originally had 2–3 review rows |

---

## 3. Marts Layer (`marts` schema) — Star Schema, Source of Truth

Full DDL: `sql/marts/01_dims.sql` (dimensions), `sql/marts/02_facts.sql` (facts).

### 3.0 Entity-relationship summary

```
                    ┌───────────────┐
                    │   dim_date     │  PK date_day (1,096 rows, 2016-01-01..2018-12-31)
                    └───────┬────────┘
                            │ FK order_purchase_date
        ┌───────────────┐  │  ┌──────────────────┐   ┌───────────────┐
        │  dim_customer  │  │  │   dim_product     │   │   dim_seller   │
        │  PK customer_  │  │  │  PK product_id    │   │  PK seller_id  │
        │  unique_id     │  │  │  (32,951 rows)    │   │  (3,095 rows)  │
        │  (96,096 rows) │  │  └─────────┬─────────┘   └───────┬────────┘
        └───────┬────────┘  │            │ FK product_id        │ FK seller_id
                │ FK customer_unique_id   │                      │
                ▼            ▼            ▼                      ▼
        ┌─────────────────────────┐   ┌─────────────────────────────────┐
        │      fact_orders         │   │      fact_order_items            │
        │  PK order_id              │◀──│  PK (order_id, order_item_id)    │
        │  (99,441 rows)            │FK │  (112,650 rows)                  │
        └───────────┬───────────────┘order_id
                     │ FK order_id
                     ▼
        ┌─────────────────────────┐
        │   fact_order_payments     │
        │  PK (order_id,             │
        │      payment_sequential)   │
        │  (103,886 rows)            │
        └─────────────────────────┘

dim_geography (PK zip_code_prefix, 19,015 rows) — standalone; joined via
*_zip_code_prefix for map/zip-level analysis independent of customer/seller role.
```

**Redshift notes:** all 5 dimensions use `DISTSTYLE ALL` (broadcast to every node — every dim is <100K rows, so every fact↔dim join is local). `fact_orders` uses `DISTKEY(customer_unique_id)` (co-locates a customer's orders for RFM/cohort joins) and `SORTKEY(order_purchase_date)` (the dominant range-filter/group-by column across all analytics). `fact_order_items` / `fact_order_payments` use `DISTKEY(order_id)` and `SORTKEY(order_purchase_date)`. Full Redshift DDL variant: `redshift/DEPLOYMENT.md`.

### 3.1 `dim_date` — 1,096 rows · PK `date_day` · 2016-01-01 to 2018-12-31

| Column | Type | Definition |
|---|---|---|
| `date_day` | DATE, **PK** | Calendar date |
| `year` | INT | `EXTRACT(YEAR FROM date_day)` |
| `quarter` | INT (1–4) | `EXTRACT(QUARTER FROM date_day)` |
| `month` | INT (1–12) | `EXTRACT(MONTH FROM date_day)` |
| `month_name` | VARCHAR | Full month name, trimmed (e.g. `"January"`) |
| `year_month` | VARCHAR | `"YYYY-MM"` |
| `iso_week` | INT | `EXTRACT(WEEK FROM date_day)` — ISO week number |
| `day_of_week` | INT (0–6) | `EXTRACT(DOW FROM date_day)` — **Sunday=0 … Saturday=6** (see §0.5) |
| `day_name` | VARCHAR | Full day name, trimmed (e.g. `"Monday"`) |
| `is_weekend` | BOOLEAN | `day_of_week IN (0, 6)` (Sat/Sun) |

### 3.2 `dim_customer` — 96,096 rows · PK `customer_unique_id`

Grain = the actual **person**. 96,096 distinct people placed 99,441 orders via 99,441 `customer_id` records — i.e. some people ordered more than once (2,888 repeat customers, per `kpi_summary.csv`). Location columns reflect the address on the customer's **most recent order** (`ROW_NUMBER() OVER (PARTITION BY customer_unique_id ORDER BY order_purchase_timestamp DESC) = 1`).

| Column | Type | Definition |
|---|---|---|
| `customer_unique_id` | VARCHAR(32), **PK** | Person-level identifier |
| `customer_zip_code_prefix` | VARCHAR(5) | 5-digit zip prefix from the customer's most recent order |
| `customer_city` | VARCHAR(100) | Lowercase city name |
| `customer_state` | VARCHAR(2) | Uppercase 2-letter Brazilian state code |
| `customer_latitude` | NUMERIC(15,10) | Centroid latitude for `customer_zip_code_prefix` from `stg_geolocation`; NULL if the zip has no geolocation match (part of the 275 customer+seller zips with no match, flagged in `docs/data_quality_report.md`) |
| `customer_longitude` | NUMERIC(15,10) | Centroid longitude, same caveat |
| `n_lifetime_orders` | INT | `COUNT(*)` of **all** orders (incl. canceled/unavailable) ever placed by this person |
| `first_order_date` | DATE | `MIN(order_purchase_timestamp)::date` across all their orders |
| `last_order_date` | DATE | `MAX(order_purchase_timestamp)::date` across all their orders |

### 3.3 `dim_product` — 32,951 rows · PK `product_id`

| Column | Type | Definition |
|---|---|---|
| `product_id` | VARCHAR(32), **PK** | |
| `product_category_name` | VARCHAR(100) | Portuguese category name; `'unknown'` if NULL in source (610 rows) |
| `product_category_name_english` | VARCHAR(100) | English translation via `product_category_translation`, with 2 manual mappings + `'unknown'` fallback (§2). This is the field used as `category` everywhere downstream |
| `product_name_length` | INT | Character length of the product name |
| `product_description_length` | INT | Character length of the product description |
| `product_photos_qty` | INT | Number of product photos |
| `product_weight_g` | INT | Package weight, grams |
| `product_length_cm` / `product_height_cm` / `product_width_cm` | INT | Package dimensions, cm |
| `product_volume_cm3` | INT | `product_length_cm × product_height_cm × product_width_cm` |
| `dq_category_missing` | BOOLEAN | TRUE if the source `product_category_name` was NULL (610 rows) |

### 3.4 `dim_seller` — 3,095 rows · PK `seller_id`

| Column | Type | Definition |
|---|---|---|
| `seller_id` | VARCHAR(32), **PK** | |
| `seller_zip_code_prefix` | VARCHAR(5) | |
| `seller_city` | VARCHAR(100) | Lowercase |
| `seller_state` | VARCHAR(2) | Uppercase 2-letter Brazilian state code |
| `seller_latitude` / `seller_longitude` | NUMERIC(15,10) | Centroid from `stg_geolocation`; NULL if no match |

### 3.5 `dim_geography` — 19,015 rows · PK `zip_code_prefix`

Standalone zip-prefix-grain table for map visualizations / regional joins independent of whether the zip belongs to a customer or seller.

| Column | Type | Definition |
|---|---|---|
| `zip_code_prefix` | VARCHAR(5), **PK** | |
| `city` | VARCHAR(100) | Most-frequently-reported city name for this prefix across all geolocation pings |
| `state` | VARCHAR(2) | Most-frequently-reported state for this prefix |
| `latitude` / `longitude` | NUMERIC(15,10) | Mean (centroid) of all pings for this prefix |

### 3.6 `fact_orders` — 99,441 rows · PK `order_id`

Grain = **1 row per order**. Aggregates items/payments/review to the order level and derives every fulfillment-timing metric used by the operations-lens analytics.

| Column | Type | Definition |
|---|---|---|
| `order_id` | VARCHAR(32), **PK** | |
| `customer_unique_id` | VARCHAR(32), FK → `dim_customer` | |
| `customer_zip_code_prefix` | VARCHAR(5) | |
| `customer_state` | VARCHAR(2) | |
| `order_status` | VARCHAR(20) | One of: `delivered` (96,478), `shipped` (1,107), `canceled` (625), `unavailable` (609), `invoiced` (314), `processing` (301), `created` (5), `approved` (2) |
| `order_purchase_timestamp` | TIMESTAMP | |
| `order_purchase_date` | DATE, FK → `dim_date` | `order_purchase_timestamp::date` |
| `order_approved_at` | TIMESTAMP | |
| `order_delivered_carrier_date` | TIMESTAMP | |
| `order_delivered_customer_date` | TIMESTAMP | |
| `order_estimated_delivery_date` | TIMESTAMP | |
| `n_items` | INT | `COUNT(*)` of `fact_order_items` rows for this order; 0 if none |
| `n_distinct_products` | INT, nullable | `COUNT(DISTINCT product_id)`; NULL if no items |
| `n_distinct_sellers` | INT, nullable | `COUNT(DISTINCT seller_id)`; NULL if no items |
| `items_price_total` | NUMERIC | `SUM(price)` across items; 0 if none |
| `freight_value_total` | NUMERIC | `SUM(freight_value)` across items; 0 if none |
| `order_total_value` | NUMERIC | `items_price_total + freight_value_total` |
| `payment_value_total` | NUMERIC, nullable | `SUM(payment_value)` across payment rows; NULL for the 1 order with no payment row |
| `max_installments` | INT, nullable | `MAX(payment_installments)` across payment rows |
| `n_payment_types` | INT, nullable | `COUNT(DISTINCT payment_type)` |
| `primary_payment_type` | VARCHAR(20), nullable | The `payment_type` with the **highest** `payment_value` (`ARRAY_AGG(payment_type ORDER BY payment_value DESC)[1]`). Distribution: `credit_card` 74,975 · `boleto` 19,784 · `voucher` 3,151 · `debit_card` 1,527 · `not_defined` 3 · NULL 1 |
| `review_score` | INT (1–5), nullable | NULL for 768 orders (0.77%) with no matching review |
| `has_review` | BOOLEAN | `review_id IS NOT NULL` |
| `approval_hours` | NUMERIC | `(order_approved_at − order_purchase_timestamp)` in fractional **hours** |
| `carrier_handoff_days` | NUMERIC | `(order_delivered_carrier_date − order_approved_at)` in fractional **days** |
| `shipping_transit_days` | NUMERIC | `(order_delivered_customer_date − order_delivered_carrier_date)` in fractional **days** |
| `actual_delivery_days` | NUMERIC | `(order_delivered_customer_date − order_purchase_timestamp)` in fractional **days** (end-to-end) |
| `estimated_delivery_days` | NUMERIC | `(order_estimated_delivery_date − order_purchase_timestamp)` in fractional **days** |
| `delivery_delay_days` | NUMERIC | `(order_delivered_customer_date − order_estimated_delivery_date)` in fractional **days**. **>0 = delivered AFTER the estimate (late); <0 = delivered BEFORE the estimate (early)** |
| `is_delivered` | BOOLEAN | `order_status = 'delivered'` |
| `is_late` | BOOLEAN (effectively nullable) | `is_delivered AND delivered_customer_date > estimated_delivery_date`. FALSE for all non-delivered orders; **NULL only for the 8 `dq_delivered_missing_date` orders** (3-valued SQL logic: `TRUE AND NULL = NULL`) |
| `is_canceled` | BOOLEAN | `order_status = 'canceled'` |
| `dq_delivered_missing_date` | BOOLEAN | TRUE for 8 orders: `status='delivered'` but `delivered_customer_date IS NULL` |
| `dq_carrier_before_approval` | BOOLEAN | TRUE for 1,359 orders (1.37%) where `delivered_carrier_date < approved_at` — a source timestamp anomaly; these rows are kept (revenue/review still valid) but **excluded from `carrier_handoff_days` averages** in `sql/analytics/03_fulfillment_ops.sql` |
| `dq_delivered_before_carrier` | BOOLEAN | TRUE for 23 orders (0.02%) where `delivered_customer_date < delivered_carrier_date` — **excluded from `shipping_transit_days` averages** |

Indexes: `order_purchase_date`, `customer_unique_id`, `customer_state`. FKs: `customer_unique_id → dim_customer`, `order_purchase_date → dim_date`.

### 3.7 `fact_order_items` — 112,650 rows · PK `(order_id, order_item_id)`

Grain = **1 row per `(order_id, order_item_id)`** — the Retail-lens fact table for revenue/category/seller analysis.

| Column | Type | Definition |
|---|---|---|
| `order_id` | VARCHAR(32), **PK part**, FK → `fact_orders` | |
| `order_item_id` | INT, **PK part** | 1-based line-item sequence number within the order |
| `product_id` | VARCHAR(32), FK → `dim_product` | |
| `seller_id` | VARCHAR(32), FK → `dim_seller` | |
| `order_purchase_date` | DATE, FK → `dim_date` | |
| `price` | NUMERIC(12,2) | Item price, **excludes freight** |
| `freight_value` | NUMERIC(12,2) | Freight charge allocated to this line item |
| `item_total_value` | NUMERIC | `price + freight_value` |
| `shipping_limit_date` | TIMESTAMP | Seller's shipping deadline for this item |

Indexes: `product_id`, `seller_id`, `order_purchase_date`.

### 3.8 `fact_order_payments` — 103,886 rows · PK `(order_id, payment_sequential)`

Grain = **1 row per `(order_id, payment_sequential)`** — payment-method/installment detail (checkout behavior: installment plans, voucher usage, split payments) that `fact_orders`' aggregates lose.

| Column | Type | Definition |
|---|---|---|
| `order_id` | VARCHAR(32), **PK part**, FK → `fact_orders` | |
| `payment_sequential` | INT, **PK part** | 1-based sequence number for split/multi-method payments |
| `order_purchase_date` | DATE, FK → `dim_date` | |
| `payment_type` | VARCHAR(20) | `credit_card` / `boleto` / `voucher` / `debit_card` / `not_defined`, lowercase |
| `payment_installments` | INT | Number of installments (1 = single payment) |
| `payment_value` | NUMERIC(12,2) | |

Indexes: `payment_type`, `order_purchase_date`.

---

## 5. Dashboard Extract Layer (`dashboard/extracts/*.csv`, 24 files)

All 24 files are generated by `etl/export_dashboard_extracts.py` directly from `marts.*` tables (re-implementing the validated logic of notebooks NB1–NB6 — **no new analytical methodology**). Two base pulls feed most extracts:

- **`orders`** (99,441 rows): `fact_orders` joined to `dim_customer` plus the **first line item's** (`order_item_id=1`) product/seller, with derived columns `customer_region`, `seller_region`, `is_cross_region`, `distance_km`, `freight_ratio`, `purchase_year`/`purchase_month`/`purchase_dow`, `is_negative_review`, `category`, `category_grp`.
- **`items`** (112,650 rows): `fact_order_items` joined to `dim_product` / `dim_seller` / `fact_orders`, with `category`, `category_grp`, `customer_region`, `seller_region`.

`category_grp` = `category` collapsed to `"other"` if it has fewer than 500 occurrences in the relevant population (or `"unknown"` if `category` is `"unknown"`) — keeps one-hot encodings (Models A/B) and category breakdowns to a manageable cardinality (the raw `category` field has ~73 distinct English category names).

### 5.1 Common Fields Glossary

Many of the ~140 distinct column names across the 24 extracts repeat verbatim (or near-verbatim) across multiple files. This glossary defines each **once**; §5.2's per-file tables reference it by section letter (e.g. "→ §D") and give full definitions only for columns that are unique to that file or whose meaning is file-dependent.

#### §A — Identifiers & Categorical Keys

| Field | Type | Definition |
|---|---|---|
| `order_id` | string | Order identifier (PK of `fact_orders` / `orders_detail.csv`) |
| `order_item_id` | int | 1-based line-item sequence number within an order (part of `fact_order_items`'s composite key) |
| `customer_unique_id` | string | Person-level customer identifier (PK of `dim_customer` / `customer_segments.csv`) |
| `product_id` | string | Product identifier (PK of `dim_product`) |
| `seller_id` | string | Seller identifier (PK of `dim_seller`) |
| `order_status` | string | Order lifecycle status, lowercase — distribution in §3.6 |
| `primary_payment_type` | string | `credit_card` / `boleto` / `voucher` / `debit_card` / `not_defined` — distribution in §3.6 |
| `category` | string | English product category (`dim_product.product_category_name_english`); `'unknown'` if missing. ~73 distinct values |
| `category_grp` | string | `category` collapsed to `"other"` if it occurs <500 times in the relevant population (or `"unknown"` if `category` is unknown) |
| `category_mix` | string | `category_monthly_mix.csv` only: top-10 categories by total revenue kept as-is, all others grouped to `"other"` |
| `feature` | string | `feature_importance_model_*.csv`: name of a model feature (a numeric feature, or a categorical feature's group name e.g. `"category_grp"`, `"purchase_month"`) |
| `model` | string | `feature_importance_model_*.csv`: `"Late Delivery Risk (Model A)"` or `"Negative Review Risk (Model B)"` |
| `segment` | string | 1 of 4 named K-Means behavioral segments — see `customer_segments.csv` (§5.2) for the full naming logic |
| `cluster` | int (0–3) | Raw K-Means cluster id. **Arbitrary across re-runs** — use `segment`, not `cluster`, for any narrative or filter |
| `rfm_segment` | string | 1 of 5 rule-based RFM segments — see `customer_segments.csv` (§5.2) |
| `risk_tier` | string | `"High Risk (top 20%)"` / `"Medium Risk (next 30%)"` / `"Low Risk (bottom 50%)"` — derived from `risk_decile` |
| `delay_bucket` | string | 1 of 5 delivery-delay buckets, with a leading digit that forces correct alphabetical sort in Tableau: `"1. Early (2+ days ahead)"`, `"2. On-time (0-1 day ahead)"`, `"3. Late 1-3 days"`, `"4. Late 4-7 days"`, `"5. Late 8+ days"` |
| `period` | string | `anomaly_state_comparison.csv` only: `"Normal (Sep-Dec 2017)"` or `"Spike (Feb-Mar 2018)"` |
| `stage` | string | `cycle_time_stages.csv` only: name of a fulfillment-cycle stage |
| `r_score` / `m_score` | int (1–5) | RFM quintile scores. `r_score`: 5 = most recent order (best). `m_score`: 5 = highest lifetime spend (best) |
| `pc1` / `pc2` | float | 1st / 2nd principal component of the 10 standardized K-Means features — unitless 2D projection for the segmentation scatter plot |

#### §B — Date / Time

| Field | Type | Definition |
|---|---|---|
| `order_purchase_date` | date | Calendar date the order was placed (`order_purchase_timestamp`, time-of-day dropped) |
| `purchase_year` | int | Year of `order_purchase_date` |
| `purchase_month` | int (1–12) | Month of `order_purchase_date` |
| `purchase_dow` | int (0–6) | pandas `.dt.dayofweek` of `order_purchase_date` — **Monday=0…Sunday=6** (different convention from `dim_date.day_of_week`; see §0.5) |
| `month` | date | First day of the calendar month — the grain for `monthly_kpis.csv`, `seasonality_analysis.csv`, `category_monthly_mix.csv` |
| `week` | date | Monday start-of-week date — the grain for `fulfillment_weekly_2018.csv` |
| `last_order_date` | date | Most recent `order_purchase_date` for a customer (`customer_segments.csv`) |
| `date_range_start` / `date_range_end` | date | `kpi_summary.csv` only: MIN / MAX `order_purchase_date` among valid orders (2016-09-04 / 2018-09-03) |

#### §C — Population & Volume Counts

| Field | Type | Definition |
|---|---|---|
| `n_orders` | int | Count of orders matching this row's grain **and** the file's stated population (valid / delivered / etc. — see §5.2 for the exact filter per file) |
| `n_delivered` | int | Count of delivered orders (§0.3) matching this row's grain |
| `n_late` | int | Count of `n_delivered` orders where `is_late = 1` |
| `n_items` | int | `orders_detail.csv`: line-item count for that order. `geo_seller_state_summary.csv` / `seller_scorecard.csv`: count of `fact_order_items` rows for that seller/state |
| `n_items_sold` | int | Count of line items sold (rows in `fact_order_items`) for a category/period |
| `n_sold` | int | `top_products.csv`: count of line items sold for one product |
| `n_distinct_products` / `n_distinct_sellers` | int, nullable | Count of distinct `product_id` / `seller_id` values within an order |
| `n_customers` | int | Count of distinct `customer_unique_id` values matching this row's grain |
| `n_sellers` | int | Count of distinct `seller_id` values matching this row's grain |
| `n_categories` | int | `customer_segments.csv`: count of distinct product categories a customer has ever purchased across their lifetime valid orders |
| `n_orders_containing` | int | `category_summary.csv`: count of distinct orders containing ≥1 item from this category (an order can count toward multiple categories) |
| `n_primary_orders` | int | `category_summary.csv`: count of orders whose **first** line item (`order_item_id=1`) belongs to this category — the denominator for `avg_review_score`/`pct_late` in that file, so multi-item orders aren't double-counted across categories |
| `total_orders` | int | `kpi_summary.csv`: total order count incl. canceled/unavailable (= 99,441). `seller_pareto_deciles.csv`: **SUM** of seller-level `n_orders` within a revenue decile — same field name, different meaning per file |
| `total_customers` | int | `kpi_summary.csv`: distinct `customer_unique_id` values (= 96,096) |
| `total_sellers` | int | `kpi_summary.csv`: distinct `seller_id` among each order's first line item across **all** 99,441 orders (= 3,088). Note this differs from both `dim_seller` (3,095 registered sellers) and `seller_scorecard.csv` (3,053 sellers with ≥1 item in a *valid* order) — see `seller_scorecard.csv` notes in §5.2 |
| `valid_orders` | int | `kpi_summary.csv`: count of valid orders (§0.3) = 98,207 |
| `repeat_customers` | int | `kpi_summary.csv`: customers with >1 lifetime valid order (= 2,888) |
| `new_customer_orders` / `returning_customer_orders` | int | `monthly_kpis.csv`: count of orders in the month that were the customer's 1st-ever order (new) vs 2nd+-ever order (returning), based on each customer's **full lifetime** order sequence (not just orders within this month) |
| `n` | int | `cycle_time_stages.csv`: count of non-null observations for that timing stage |

#### §D — Revenue / GMV / Monetary (currency: Brazilian Real, R$/BRL — no FX conversion)

| Field | Type | Definition |
|---|---|---|
| `gmv` | float | Gross Merchandise Value = `SUM(order_total_value)` for valid orders in this row's grain (time period or geography) |
| `revenue` | float | `SUM(price)` at the line-item grain (**excludes freight**) for this row's grain (category / seller / product / state) |
| `total_gmv` | float | `kpi_summary.csv`: GMV across all valid orders (= R$15,735,527.03) |
| `total_revenue` | float | `rfm_segment_summary.csv`: `SUM(monetary)` across all customers in this RFM segment |
| `order_total_value` | float | `items_price_total + freight_value_total` for one order |
| `items_price_total` | float | `SUM(price)` across an order's line items |
| `freight_value_total` / `freight_value` | float | `SUM(freight_value)` across an order's items / one line item's freight charge |
| `item_total_value` | float | `price + freight_value` for a single line item |
| `price` | float | A single line item's product price (**excludes freight**) |
| `monetary` | float | RFM "Monetary": `SUM(order_total_value)` across a customer's lifetime valid orders |
| `cumulative_gmv` | float | `monthly_kpis.csv`: running cumulative sum of `gmv` across months, chronological order |
| `gmv_3mo_moving_avg` | float | `monthly_kpis.csv`: trailing 3-month average of `gmv` **including** the current month (`.rolling(3).mean()`) |
| `trailing_3mo_avg_gmv` | float | `seasonality_analysis.csv`: 3-month average of the **prior** 3 months' `gmv`, **excluding** the current month (`.shift(1).rolling(3).mean()`) — the seasonal baseline for `pct_above_trailing_avg` |
| `month_total` | float | `category_monthly_mix.csv`: total revenue across **all** categories in that month — denominator for `share_of_month` |

#### §E — Averages / Ratios / Per-Unit

| Field | Type | Scale | Definition |
|---|---|---|---|
| `aov` | float | BRL | Average Order Value = `gmv / n_orders` |
| `avg_order_value` | float | BRL | `customer_segments.csv`: this customer's personal AOV = `monetary / frequency` |
| `avg_price` | float | BRL | `top_products.csv`: `mean(price)` across a product's line items |
| `avg_revenue_per_order` | float | BRL | `seller_scorecard.csv`: seller `revenue / n_orders` |
| `freight_ratio` | float | **0.0–1.0** | `freight_value_total / order_total_value` for one order — **not** a `pct_*` field; use built-in Percentage format if displayed as % |
| `avg_freight_ratio` | float | **0.0–1.0** | Mean `freight_ratio` across the orders/customers in this row's grain |
| `max_installments` | int | months | Highest `payment_installments` across an order's payment rows |
| `avg_installments` | float | months | `customer_segments.csv`: a customer's mean `max_installments` across their lifetime orders |

#### §F — Fulfillment Timing (fractional days unless noted)

| Field | Type | Definition |
|---|---|---|
| `actual_delivery_days` | float | `order_purchase_timestamp → order_delivered_customer_date`, fractional days (end-to-end) |
| `estimated_delivery_days` | float | `order_purchase_timestamp → order_estimated_delivery_date`, fractional days |
| `delivery_delay_days` | float | `order_delivered_customer_date − order_estimated_delivery_date`, fractional days. **>0 = late, <0 = early** |
| `avg_actual_delivery_days` / `avg_delay_days` / `avg_delivery_delay_days` | float | Row-grain means of the corresponding per-order field above |
| `distance_km` | float | Haversine great-circle distance (km) between the customer's and (first-item) seller's zip-prefix centroids |
| `avg_distance_km` | float | Mean `distance_km` across the orders in this row's grain |
| `n` / `avg_value` / `median_value` / `p90_value` / `unit` / `stage_order` | mixed | `cycle_time_stages.csv` only — `n`=observation count, `avg`/`median`/`p90`=stage duration stats, `unit`=`"hours"`\|`"days"`, `stage_order`=1–4 display ordering |

#### §G — On-Time Delivery / Late Flags

| Field | Type | Scale | Definition |
|---|---|---|---|
| `is_late` | int | 0/1, nullable | `is_delivered AND delivered_customer_date > estimated_delivery_date`. See §3.6 for the 8-order NULL edge case |
| `is_delivered` | int | 0/1 | `order_status = 'delivered'` |
| `is_canceled` | int | 0/1 | `order_status = 'canceled'` |
| `pct_late` | float | **0–100** | `100 × mean(is_late)` over the delivered orders in this row's grain |
| `pct_late_overall` | float | **0–100** | `kpi_summary.csv`: `pct_late` across all delivered orders (= 8.11) |
| `is_cross_region` | int | 0/1, nullable | `customer_region != seller_region` (NA if `seller_region` is unknown) |

#### §H — Review / Satisfaction

| Field | Type | Scale | Definition |
|---|---|---|---|
| `review_score` | int | 1–5, nullable | Customer's review score for the order (NULL for 0.77% of orders) |
| `has_review` | int | 0/1 | `review_score IS NOT NULL` |
| `is_negative_review` / `is_negative` | int | 0/1, nullable | `review_score <= 2`. NULL/NA when `has_review = 0` (only relevant in `orders_detail.csv` — `risk_scores_negative_review.csv` is pre-filtered to reviewed orders) |
| `avg_review_score` | float | 1.0–5.0 | Mean `review_score` over the **reviewed** orders in this row's grain |
| `avg_review_score_overall` | float | 1.0–5.0 | `kpi_summary.csv`: mean `review_score` over all valid+reviewed orders (= 4.116) |
| `pct_negative_review_overall` | float | **0–100** | `kpi_summary.csv`: % of valid+reviewed orders with `review_score <= 2` (= 13.77) |
| `pct_1star` / `pct_5star` | float | **0–100** | `delay_bucket_vs_review.csv`: % of reviews in this delay bucket that are 1-star / 5-star |

#### §I — Distribution / Pareto / Ranking

| Field | Type | Scale | Definition |
|---|---|---|---|
| `revenue_rank` / `gmv_rank` | int | 1..N | Dense rank by `revenue` / `gmv`, descending (1 = highest) |
| `pct_of_total_revenue` / `pct_of_total_gmv` | float | **0–100** | This row's `revenue`/`gmv` as a % of the sum across all rows in the file |
| `cumulative_pct_of_revenue` / `cumulative_pct_gmv` / `cumulative_pct` | float | **0–100** | Running cumulative sum of `pct_of_total_revenue`/`pct_of_total_gmv`, in descending order — **the same concept under 3 different names**: `cumulative_pct_of_revenue` (`category_summary.csv`, `seller_pareto_deciles.csv`), `cumulative_pct_gmv` (`geo_customer_state_summary.csv`), `cumulative_pct` (`geo_seller_state_summary.csv`) |
| `revenue_decile` / `decile_revenue` | int / float | 1–10 / BRL | `revenue_decile`: seller's revenue decile where **1 = HIGHEST revenue** (`10 - pd.qcut(...)`, inverted so decile 1 reads as "top sellers"). `decile_revenue` (`seller_pareto_deciles.csv`): `SUM(revenue)` of all sellers in that decile |
| `gmv_mom_pct` | float | signed pp | `monthly_kpis.csv`: month-over-month % change in `gmv` (`.pct_change() × 100`) |
| `pct_above_trailing_avg` | float | signed pp | `seasonality_analysis.csv`: `(gmv − trailing_3mo_avg_gmv) / trailing_3mo_avg_gmv × 100` |
| `is_seasonal_spike` | int | 0/1 | `seasonality_analysis.csv`: `gmv > 1.3 × trailing_3mo_avg_gmv` |
| `is_full_month` | int | 0/1 | `monthly_kpis.csv`: `month` is between 2017-01-01 and 2018-08-01 inclusive (excludes the partial ramp-up months Sep–Dec 2016 and the partial cutoff months Sep–Oct 2018) |
| `share_of_month` | float | **0–100** | `category_monthly_mix.csv`: this category's `revenue / month_total × 100` |

#### §J — Customer Segmentation (RFM + K-Means + PCA)

| Field | Type | Definition |
|---|---|---|
| `frequency` | int | RFM "Frequency": count of a customer's lifetime valid orders |
| `recency_days` / `avg_recency_days` | float | Days between the customer's `last_order_date` and the snapshot date (= max `order_purchase_date` across all valid orders, **+1 day** = 2018-09-04) |
| `is_repeat` | int (0/1) | `frequency > 1` |
| `pct_customers` | float (0–100) | This segment's customer count as a % of all customers in the file |
| `pct_revenue` | float (0–100) | This segment's total `monetary` as a % of total `monetary` across all customers |
| `pct_repeat` | float (0–100) | % of customers in this segment with `is_repeat = 1` |
| `avg_monetary` | float (BRL) | `rfm_segment_summary.csv`: `mean(monetary)` for customers in this RFM segment |

#### §K — Predictive Risk Models (Page 7)

| Field | Type | Scale | Definition |
|---|---|---|---|
| `predicted_late_risk` | float | **0.0–1.0** | Model A (RandomForest, 200 trees, `max_depth=8`, `class_weight="balanced"`): predicted probability this order is delivered late, using **only order-time features** (no post-delivery information). Held-out AUC=0.7422, PR-AUC=0.2153 |
| `predicted_negative_review_risk` | float | **0.0–1.0** | Model B (same architecture): predicted probability of `review_score <= 2`, using post-delivery features (incl. `is_late`, `delivery_delay_days`). Held-out AUC=0.745, PR-AUC=0.270 |
| `risk_decile` | int | 1–10 | Decile of the model's predicted risk, where **1 = HIGHEST risk** (`10 - pd.qcut(...)`, inverted) |
| `risk_tier` | string | — | `"High Risk (top 20%)"` (decile 1–2) / `"Medium Risk (next 30%)"` (decile 3–5) / `"Low Risk (bottom 50%)"` (decile 6–10) |
| `importance` | float | 0.0–1.0 | `feature_importance_model_*.csv`: this feature's RandomForest `feature_importances_` value, with one-hot dummy importances summed back to their parent categorical feature |
| `pct_of_total_importance` | float | **0–100** | `importance` as a % of the sum of all 11 features' importance for that model |
| `rank` | int | 1–11 | Dense rank by `importance`, descending |

#### §L — Geography

| Field | Type | Definition |
|---|---|---|
| `customer_state` / `seller_state` | string (2 chars) | Uppercase 2-letter Brazilian state code |
| `customer_state_name` / `seller_state_name` / `state_name` | string | Full Portuguese state name (`BR_STATE_NAME`, §0.6) — for Tableau geocoding |
| `customer_region` / `seller_region` / `region` | string | 1 of 5 IBGE macro-regions (`BR_REGION`, §0.6) |
| `customer_city` | string | Lowercase city name |

---

### 5.2 Per-File Catalog

#### Page 1 — Executive Overview

##### `monthly_kpis.csv` — 24 rows, 1 row per calendar month

**Population:** valid orders (§0.3), grouped by `order_purchase_date`'s month. `n_delivered`/`n_late`/`avg_actual_delivery_days`/`avg_delay_days`/`pct_late` are computed over the subset of those orders that are delivered with a non-null `delivery_delay_days`; `avg_review_score` over the reviewed subset.

**⚠ Data note:** spans Sep-2016 through Sep-2018 (25 calendar months) but only **24 rows** — **November 2016 has zero valid orders** and is silently absent from the groupby (a known gap in the underlying Olist dataset, not a pipeline bug). Anyone building a continuous monthly time series in Tableau should pad this gap explicitly (e.g. via a `dim_date`-driven blank row) or the line chart will visually interpolate straight across it.

**Purpose:** Monthly trend of GMV, order volume, AOV, on-time-delivery rate, review score, and new-vs-returning customer mix — feeds the Page 1 executive trend charts.

| # | Column | Glossary | Notes |
|---|---|---|---|
| 1 | `n_orders` | §C | |
| 2 | `gmv` | §D | |
| 3 | `month` | §B | |
| 4 | `n_delivered` | §C | |
| 5 | `n_late` | §C | |
| 6 | `avg_actual_delivery_days` | §F | |
| 7 | `avg_delay_days` | §F | |
| 8 | `avg_review_score` | §H | |
| 9 | `new_customer_orders` | §C | |
| 10 | `returning_customer_orders` | §C | |
| 11 | `aov` | §E | |
| 12 | `pct_late` | §G | |
| 13 | `pct_orders_from_returning` | — | **Unique to this file.** `100 × returning_customer_orders / n_orders`. Scale 0–100 |
| 14 | `gmv_mom_pct` | §I | |
| 15 | `gmv_3mo_moving_avg` | §D | |
| 16 | `cumulative_gmv` | §D | |
| 17 | `is_full_month` | §I | |

##### `seasonality_analysis.csv` — 17 rows, 1 row per calendar month (Apr-2017 to Aug-2018)

**Population:** valid orders, restricted to the 20 "full" calendar months (Jan-2017 through Aug-2018, `is_full_month=True` in `monthly_kpis.csv`), then the **first 3 of those 20 months are dropped** because `trailing_3mo_avg_gmv` needs 3 prior full months of history (`.shift(1).rolling(3)`) — leaving 17 rows, Apr-2017 through Aug-2018.

**Purpose:** De-trended monthly GMV vs. its trailing 3-month baseline, used to identify seasonal spikes (e.g. the Nov-2017 Black Friday spike, `is_seasonal_spike=True`).

| # | Column | Glossary | Notes |
|---|---|---|---|
| 1 | `month` | §B | |
| 2 | `gmv` | §D | |
| 3 | `n_orders` | §C | |
| 4 | `trailing_3mo_avg_gmv` | §D | |
| 5 | `pct_above_trailing_avg` | §I | |
| 6 | `is_seasonal_spike` | §I | |

##### `kpi_summary.csv` — 1 row (headline KPI tiles)

**Population:** mixed — see per-column notes. This is the single-row dataset that drives every "Big-Ass-Number" tile at the top of Page 1.

| # | Column | Glossary | Notes |
|---|---|---|---|
| 1 | `total_orders` | §C | All 99,441 orders, incl. canceled/unavailable |
| 2 | `valid_orders` | §C | 98,207 — excludes canceled/unavailable |
| 3 | `total_customers` | §C | 96,096 distinct `customer_unique_id` |
| 4 | `repeat_customers` | §C | 2,888 customers with >1 lifetime valid order |
| 5 | `repeat_rate_pct` | — | **Unique to this file.** `100 × repeat_customers / total_customers` = 3.01. Scale 0–100 |
| 6 | `total_gmv` | §D | R$15,735,527.03 |
| 7 | `aov` | §E | `total_gmv / valid_orders` = R$160.23 |
| 8 | `pct_late_overall` | §G | 8.11 |
| 9 | `avg_review_score_overall` | §H | 4.116 |
| 10 | `pct_negative_review_overall` | §H | 13.77 |
| 11 | `total_sellers` | §C | 3,088 — see §C note on the 3 different seller counts in this project |
| 12 | `date_range_start` | §B | 2016-09-04 |
| 13 | `date_range_end` | §B | 2018-09-03 |

---

#### Page 2 — Sales & Category Performance

##### `category_summary.csv` — 74 rows, 1 row per product category

**Population:** revenue/unit columns (`n_items_sold`, `n_orders_containing`, `revenue`, `pct_of_total_revenue`, `cumulative_pct_of_revenue`, `revenue_rank`) computed over **line items belonging to valid orders**; quality columns (`n_primary_orders`, `avg_review_score`, `pct_late`) computed over **delivered, reviewed orders whose FIRST line item (`order_item_id=1`)** belongs to this category (so multi-item, multi-category orders aren't double-counted in the quality metrics).

**Purpose:** Revenue/units Pareto plus quality (review score, late rate) per product category — the main Page 2 category breakdown table/treemap, and the source of the "categories with the highest revenue tend to also have higher late rates" findings.

| # | Column | Glossary | Notes |
|---|---|---|---|
| 1 | `category` | §A | 74 rows = ~73 English category names + `'unknown'` |
| 2 | `n_items_sold` | §C | |
| 3 | `n_orders_containing` | §C | |
| 4 | `revenue` | §D | |
| 5 | `pct_of_total_revenue` | §I | |
| 6 | `cumulative_pct_of_revenue` | §I | |
| 7 | `revenue_rank` | §I | |
| 8 | `n_primary_orders` | §C | |
| 9 | `avg_review_score` | §H | |
| 10 | `pct_late` | §G | |

##### `category_monthly_mix.csv` — 220 rows, 1 row per `(month, category_mix)`

**Population:** line items belonging to valid orders, restricted to the 20 full calendar months (2017-01 to 2018-08). `category_mix` = the top-10 categories by total revenue across the whole window, kept individually; all remaining categories collapsed to `"other"` → 11 `category_mix` values × 20 months = 220 rows.

**Purpose:** Top-10 category revenue mix over time (100%-stacked area/bar) — shows category-mix shift across the order history, e.g. the rise of `bed_bath_table` and `health_beauty`.

| # | Column | Glossary | Notes |
|---|---|---|---|
| 1 | `category_mix` | §A | |
| 2 | `revenue` | §D | This `category_mix`'s revenue in this month |
| 3 | `n_items_sold` | §C | |
| 4 | `month` | §B | |
| 5 | `month_total` | §D | |
| 6 | `share_of_month` | §I | |

##### `top_products.csv` — 50 rows, 1 row per product (top 50 by revenue)

**Population:** line items belonging to valid orders, grouped by `(product_id, category)`, sorted by `revenue` descending, head(50).

**Purpose:** Top-50 products by revenue — drill-through table for "what are our best sellers" questions.

| # | Column | Glossary | Notes |
|---|---|---|---|
| 1 | `product_id` | §A | |
| 2 | `category` | §A | |
| 3 | `n_sold` | §C | |
| 4 | `revenue` | §D | |
| 5 | `avg_price` | §E | |
| 6 | `revenue_rank` | §I | 1–50 |

---

#### Page 3 — Geography

##### `geo_customer_state_summary.csv` — 27 rows, 1 row per customer state (26 states + DF)

**Population:** `n_customers`/`n_orders`/`gmv`/`aov`/`pct_of_total_gmv`/`cumulative_pct_gmv`/`gmv_rank` over **valid orders**; `n_delivered`/`pct_late`/`avg_actual_delivery_days`/`avg_delay_days`/`avg_distance_km` over **delivered orders**; `avg_review_score` over **delivered + reviewed orders** — all grouped by `customer_state`.

**Purpose:** Demand-side state-level summary — GMV concentration, AOV, on-time-delivery rate, delivery distance, and review score by customer state. Feeds the Page 3 choropleth and state ranking table.

| # | Column | Glossary | Notes |
|---|---|---|---|
| 1 | `customer_state` | §L | |
| 2 | `state_name` | §L | |
| 3 | `n_customers` | §C | |
| 4 | `n_orders` | §C | |
| 5 | `gmv` | §D | |
| 6 | `region` | §L | |
| 7 | `aov` | §E | |
| 8 | `pct_of_total_gmv` | §I | |
| 9 | `cumulative_pct_gmv` | §I | |
| 10 | `gmv_rank` | §I | |
| 11 | `n_delivered` | §C | |
| 12 | `pct_late` | §G | |
| 13 | `avg_actual_delivery_days` | §F | |
| 14 | `avg_delay_days` | §F | |
| 15 | `avg_distance_km` | §F | |
| 16 | `avg_review_score` | §H | |

##### `geo_seller_state_summary.csv` — 23 rows, 1 row per seller state

**Population:** line items belonging to valid orders, grouped by `seller_state`. Only 23 of the 27 Brazilian states have any registered sellers with items in this dataset (4 states have zero seller-side presence).

**Purpose:** Supply-side state-level summary — seller count, item volume, revenue, and revenue concentration by seller state. Shows the extreme seller concentration in São Paulo (Southeast).

| # | Column | Glossary | Notes |
|---|---|---|---|
| 1 | `seller_state` | §L | |
| 2 | `state_name` | §L | |
| 3 | `n_sellers` | §C | |
| 4 | `n_items` | §C | |
| 5 | `revenue` | §D | |
| 6 | `region` | §L | |
| 7 | `pct_of_total_revenue` | §I | |
| 8 | `cumulative_pct` | §I | Same concept as `cumulative_pct_of_revenue` — see §I |
| 9 | `revenue_rank` | §I | |

##### `region_flow_matrix.csv` — 23 rows, 1 row per `(customer_region, seller_region)` pair

**Population:** delivered orders with a known `seller_region`, grouped by `(customer_region, seller_region)`. Only **23 of the 25 possible (5×5) region pairs** have ≥1 such order in this dataset — `Central-West←North` and `North←North` have zero delivered orders with a North-region seller and are absent (not filtered out — they simply never occurred).

**Purpose:** Demand-vs-supply geography flow matrix — which customer regions are served by which seller regions, with on-time-delivery rate, distance, and freight ratio per flow. Powers the Page 3 region-to-region flow/heatmap (e.g. Southeast→Southeast is by far the largest flow at 56,305 orders).

| # | Column | Glossary | Notes |
|---|---|---|---|
| 1 | `customer_region` | §L | |
| 2 | `seller_region` | §L | |
| 3 | `n_orders` | §C | |
| 4 | `pct_late` | §G | |
| 5 | `avg_distance_km` | §F | |
| 6 | `avg_freight_ratio` | §E | |
| 7 | `is_cross_region` | §G | Here a plain boolean derived from `customer_region != seller_region` for the pair (not nullable, since `seller_region` is known by construction) |

---

#### Page 4 — Delivery & Fulfillment Operations

##### `cycle_time_stages.csv` — 4 rows, 1 row per fulfillment-cycle stage

**Population:** computed directly against the database (not via the shared `orders`/`items` pulls) for exact percentiles via `PERCENTILE_CONT`. Each stage has its own population, matching the `dq_*` exclusions in `fact_orders` (§3.6):

| `stage_order` | `stage` | Population (n) |
|---|---|---|
| 1 | `approval_hours (purchase -> approved)` | `order_approved_at IS NOT NULL` (n=99,281) |
| 2 | `carrier_handoff_days (approved -> carrier)` | `order_delivered_carrier_date IS NOT NULL AND NOT dq_carrier_before_approval` (n=96,299) |
| 3 | `shipping_transit_days (carrier -> customer)` | `order_delivered_customer_date IS NOT NULL AND order_delivered_carrier_date IS NOT NULL AND NOT dq_delivered_before_carrier` (n=96,452) |
| 4 | `actual_delivery_days (purchase -> customer, end-to-end)` | `is_delivered AND NOT dq_delivered_missing_date` (n=96,470) |

**Purpose:** Avg/median/p90 duration of each stage of the order lifecycle — identifies where time is spent (e.g. `shipping_transit_days` median=7.1 days dominates vs. `carrier_handoff_days` median=1.85 days).

| # | Column | Glossary | Notes |
|---|---|---|---|
| 1 | `stage` | §A | |
| 2 | `n` | §C | |
| 3 | `avg_value` | §F | |
| 4 | `median_value` | §F | |
| 5 | `p90_value` | §F | |
| 6 | `unit` | §F | `"hours"` for stage 1, `"days"` for stages 2–4 |
| 7 | `stage_order` | §F | |

##### `delay_bucket_vs_review.csv` — 5 rows, 1 row per delay bucket

**Population:** delivered + reviewed orders (n=95,824), bucketed on `delivery_delay_days` via `pd.cut(bins=[-inf,-2,0,3,7,inf])`.

**Purpose:** Shows how review score (and 1★/5★ share) degrades as delivery delay increases. This is the evidentiary basis for the case study's headline finding: orders delayed 4+ days are **5.24%** of reviewed deliveries (5,025/95,824) but account for **29.6%** of all negative reviews (3,637/12,275) — see `docs/CASE_STUDY.md` §4.4.

| # | Column | Glossary | Notes |
|---|---|---|---|
| 1 | `delay_bucket` | §A | |
| 2 | `n_orders` | §C | |
| 3 | `avg_review_score` | §H | |
| 4 | `pct_1star` | §H | |
| 5 | `pct_5star` | §H | |

##### `fulfillment_weekly_2018.csv` — 13 rows, 1 row per ISO week

**Population:** delivered orders with `order_purchase_date` between 2018-01-15 and 2018-04-15, grouped by ISO week (Monday start).

**Purpose:** Weekly on-time-delivery rate around the Feb–Mar 2018 anomaly (the "Carnival hypothesis" investigated in NB3/NB4) — drill-down detail behind Page 4's anomaly callout.

| # | Column | Glossary | Notes |
|---|---|---|---|
| 1 | `week` | §B | |
| 2 | `n_delivered` | §C | |
| 3 | `n_late` | §C | |
| 4 | `avg_actual_delivery_days` | §F | |
| 5 | `pct_late` | §G | |

##### `anomaly_state_comparison.csv` — 48 rows, 1 row per `(customer_state, period)`

**Population:** delivered orders in two windows — `"Normal (Sep-Dec 2017)"` and `"Spike (Feb-Mar 2018)"` — grouped by `customer_state`, **filtered to states with `n_delivered >= 20` in that period** (25 states qualify in the Normal period, 23 in the Spike period; 25 distinct states appear overall).

**Purpose:** State-level on-time-delivery comparison between a normal baseline and the Feb–Mar 2018 spike — shows which states drove the anomaly (vs. a uniform nationwide effect).

| # | Column | Glossary | Notes |
|---|---|---|---|
| 1 | `customer_state` | §L | |
| 2 | `n_delivered` | §C | |
| 3 | `pct_late` | §G | |
| 4 | `period` | §A | |

---

#### Page 5 — Customer Segmentation (RFM + K-Means + PCA)

##### `customer_segments.csv` — 92,746 rows, 1 row per customer (`customer_unique_id`)

**Population:** customers (subset of `dim_customer`'s 96,096) with **at least one delivered AND reviewed valid order** — i.e. `avg_review_score`, `avg_delivery_delay_days`, `avg_freight_ratio`, and `avg_installments` are all non-null. **3,350 of the 96,096 customers (3.5%) are excluded** — these are customers whose orders were all canceled/undelivered/unreviewed, so no behavioral feature set could be built for them.

**Purpose:** The master Page 5 dataset — customer-grain RFM features, K-Means cluster assignment (4 clusters), rule-based RFM segment, and a 2D PCA projection for the segmentation scatter plot. Every other Page 5 extract (`segment_profile_summary.csv`, `rfm_segment_summary.csv`) is an aggregate of this file.

**RFM segment assignment** (`rfm_segment`, rule-based on RFM quintiles `r_score`/`m_score`, evaluated in this order):

| Condition | `rfm_segment` |
|---|---|
| `r_score >= 4 AND m_score >= 4` | Champions (recent + high spend) |
| `r_score <= 2 AND m_score >= 4` | High-Value Lapsed (win-back priority) |
| `r_score >= 4 AND m_score <= 2` | New/Recent Low-Spend |
| `r_score <= 2 AND m_score <= 2` | Low-Value Lapsed |
| *(everything else)* | Mid-Value |

**K-Means segment naming** (`segment`, 4 clusters via `KMeans(n_clusters=4, random_state=42, n_init=10)` on 10 standardized features: `log_recency`, `log_monetary`, `log_avg_order_value`, `frequency`, `avg_review_score`, `avg_delivery_delay_days`, `pct_late`, `avg_freight_ratio`, `avg_installments`, `n_categories`). Raw cluster ids (`cluster`, 0–3) are **arbitrary across re-runs**, so names are assigned dynamically by characteristic, in this priority order:

| Priority | Segment name | Selection rule | Resulting size |
|---|---|---|---|
| 1 | Loyal Repeat Customers | Highest `pct_repeat` (≈70% vs. a ≈1–2% baseline elsewhere — the most extreme/unambiguous signal, picked first) | 2,347 (2.53%) |
| 2 | At-Risk: Late & Unhappy | Of what remains, highest `avg_delivery_delay_days` (most positive = latest deliveries) | 7,319 (7.89%) |
| 3 | Core High-Value | Of what remains, highest `pct_revenue` (share of total `monetary` — not necessarily the highest *per-customer* average, since a small niche cluster can have a higher ticket size but matter less to total GMV) | 41,266 (44.49%) |
| 4 | Budget Satisfied | Whatever remains | 41,814 (45.08%) |

| # | Column | Glossary | Notes |
|---|---|---|---|
| 1 | `customer_unique_id` | §A | |
| 2 | `customer_state` | §L | |
| 3 | `state_name` | §L | |
| 4 | `region` | §L | |
| 5 | `last_order_date` | §B | |
| 6 | `recency_days` | §J | |
| 7 | `frequency` | §J | |
| 8 | `monetary` | §D | |
| 9 | `avg_order_value` | §E | |
| 10 | `avg_review_score` | §H | |
| 11 | `avg_delivery_delay_days` | §F | |
| 12 | `pct_late` | §G | |
| 13 | `avg_freight_ratio` | §E | |
| 14 | `avg_installments` | §E | |
| 15 | `n_categories` | §C | |
| 16 | `is_repeat` | §J | |
| 17 | `r_score` | §A | |
| 18 | `m_score` | §A | |
| 19 | `rfm_segment` | §A | See rule table above |
| 20 | `cluster` | §A | Raw K-Means id 0–3 — arbitrary, use `segment` instead |
| 21 | `segment` | §A | See naming table above |
| 22 | `pc1` | §A | |
| 23 | `pc2` | §A | |

##### `segment_profile_summary.csv` — 4 rows, 1 row per K-Means segment

**Population:** same 92,746 customers as `customer_segments.csv`, grouped by `segment`.

**Purpose:** Per-segment profile — for each of the 4 named segments, the **mean** of all 10 clustering features plus size/revenue/repeat shares. Feeds the Page 5 segment comparison table and radar/parallel-coordinates chart. **Note:** unlike `customer_segments.csv` where `recency_days`/`frequency`/`monetary`/etc. are per-customer values, here every numeric column except the `n_*`/`pct_*` columns is a **segment-level mean**.

| # | Column | Glossary | Notes |
|---|---|---|---|
| 1 | `segment` | §A | |
| 2 | `n_customers` | §C | |
| 3 | `recency_days` | §J | Segment mean of `customer_segments.recency_days` |
| 4 | `frequency` | §J | Segment mean of `customer_segments.frequency` |
| 5 | `monetary` | §D | Segment mean of `customer_segments.monetary` |
| 6 | `avg_order_value` | §E | Segment mean |
| 7 | `avg_review_score` | §H | Segment mean |
| 8 | `avg_delivery_delay_days` | §F | Segment mean |
| 9 | `pct_late` | §G | Segment mean of each customer's `pct_late` (i.e. a mean-of-means, not re-derived from raw delivered-order counts) |
| 10 | `avg_freight_ratio` | §E | Segment mean |
| 11 | `avg_installments` | §E | Segment mean |
| 12 | `n_categories` | §C | Segment mean (note: shown as a float, e.g. 1.0014, not an int) |
| 13 | `pct_customers` | §J | |
| 14 | `pct_revenue` | §J | |
| 15 | `pct_repeat` | §J | |

##### `rfm_segment_summary.csv` — 5 rows, 1 row per RFM segment

**Population:** same 92,746 customers, grouped by `rfm_segment`.

**Purpose:** Per-RFM-segment summary — size, average monetary/recency, total revenue share, and repeat rate. Feeds the Page 5 RFM segment breakdown (e.g. Champions = 16.5% of customers but 30.6% of revenue; Mid-Value = 36.0% of customers but only 29.4% of revenue).

| # | Column | Glossary | Notes |
|---|---|---|---|
| 1 | `rfm_segment` | §A | |
| 2 | `n_customers` | §C | |
| 3 | `avg_monetary` | §J | |
| 4 | `avg_recency_days` | §J | |
| 5 | `total_revenue` | §D | |
| 6 | `pct_repeat` | §J | |
| 7 | `pct_customers` | §J | |
| 8 | `pct_revenue` | §J | |

---

#### Page 6 — Seller Marketplace

##### `seller_scorecard.csv` — 3,053 rows, 1 row per seller (`seller_id`)

**Population:** sellers with ≥1 line item in a valid order (3,053 of `dim_seller`'s 3,095 — 42 registered sellers have zero items in valid orders, e.g. they only appear in canceled orders or not at all in `order_items`). `n_delivered`/`pct_late` further restrict to that seller's items belonging to delivered, non-`dq_delivered_*`-flagged orders.

**Purpose:** Per-seller scorecard — revenue, item/order volume, review score, on-time-delivery rate, and revenue decile/rank. Feeds the Page 6 seller table and revenue-vs-quality scatter.

| # | Column | Glossary | Notes |
|---|---|---|---|
| 1 | `seller_id` | §A | |
| 2 | `seller_state` | §L | |
| 3 | `state_name` | §L | |
| 4 | `n_orders` | §C | `COUNT(DISTINCT order_id)` across this seller's items |
| 5 | `n_items` | §C | `COUNT(*)` of this seller's line items (≥ `n_orders` if the seller has multiple items in the same order) |
| 6 | `revenue` | §D | |
| 7 | `avg_review_score` | §H | |
| 8 | `n_delivered` | §C | |
| 9 | `pct_late` | §G | |
| 10 | `region` | §L | |
| 11 | `avg_revenue_per_order` | §E | |
| 12 | `revenue_decile` | §I | 1 = highest-revenue decile |
| 13 | `revenue_rank` | §I | 1–3,053 |

##### `seller_pareto_deciles.csv` — 10 rows, 1 row per revenue decile

**Population:** same 3,053 sellers, grouped by `revenue_decile`.

**Purpose:** Seller revenue concentration (Pareto) — e.g. decile 1 (the top 10% of sellers by revenue, n=306) generates **67.5%** of total marketplace revenue, illustrating extreme seller concentration.

| # | Column | Glossary | Notes |
|---|---|---|---|
| 1 | `revenue_decile` | §I | |
| 2 | `n_sellers` | §C | |
| 3 | `total_orders` | §C | **Sum of `seller_scorecard.n_orders`** across all sellers in this decile — not a deduplicated order count, so summing across deciles can exceed 99,441 if a single order has items from sellers in different deciles |
| 4 | `decile_revenue` | §I | |
| 5 | `pct_of_total_revenue` | §I | |
| 6 | `cumulative_pct_of_revenue` | §I | |

---

#### Page 7 — Predictive Risk Scoring

##### `risk_scores_late_delivery.csv` — 94,726 rows, 1 row per order (Model A population)

**Population:** delivered, **single-seller** orders (`n_distinct_sellers = 1`) with non-null `is_late` and `estimated_delivery_days`, and known customer + seller geocoordinates (needed for `distance_km`). This is Model A's training/scoring population — 94,726 of 96,470 delivered orders (1,744 excluded: multi-seller orders or missing geocoordinates).

**Purpose:** Order-level Model A (`predicted_late_risk`) risk scores, decile, and tier — feeds the Page 7 risk-scoring table, scatter, and drill-through. Model A uses **order-time-only features** (no information that wouldn't be known at the moment of purchase), making it actionable for proactive intervention (e.g. flag-and-expedite at checkout).

| # | Column | Glossary | Notes |
|---|---|---|---|
| 1 | `order_id` | §A | |
| 2 | `order_purchase_date` | §B | |
| 3 | `customer_state` | §L | |
| 4 | `state_name` | §L | |
| 5 | `customer_region` | §L | |
| 6 | `category_grp` | §A | |
| 7 | `order_total_value` | §D | |
| 8 | `estimated_delivery_days` | §F | |
| 9 | `distance_km` | §F | |
| 10 | `freight_ratio` | §E | |
| 11 | `is_late` | §G | Ground truth (actual outcome) |
| 12 | `predicted_late_risk` | §K | Model A predicted probability |
| 13 | `risk_decile` | §K | |
| 14 | `risk_tier` | §K | |

##### `risk_scores_negative_review.csv` — 95,824 rows, 1 row per order (Model B population)

**Population:** delivered orders with non-null `review_score` and `delivery_delay_days` — 95,824 of 96,470 delivered orders (646 excluded: no review or no delivery-delay value). This is Model B's training/scoring population.

**Purpose:** Order-level Model B (`predicted_negative_review_risk`) risk scores, decile, and tier. Model B uses **post-delivery features** (incl. `is_late`, `delivery_delay_days`) and is intended for retrospective triage / proactive customer-service outreach on orders that are late but not yet reviewed.

| # | Column | Glossary | Notes |
|---|---|---|---|
| 1 | `order_id` | §A | |
| 2 | `order_purchase_date` | §B | |
| 3 | `customer_state` | §L | |
| 4 | `state_name` | §L | |
| 5 | `customer_region` | §L | |
| 6 | `category_grp` | §A | |
| 7 | `order_total_value` | §D | |
| 8 | `is_late` | §G | |
| 9 | `delivery_delay_days` | §F | |
| 10 | `freight_ratio` | §E | |
| 11 | `n_distinct_sellers` | §C | |
| 12 | `review_score` | §H | |
| 13 | `is_negative` | §H | Ground truth (actual outcome) |
| 14 | `predicted_negative_review_risk` | §K | Model B predicted probability |
| 15 | `risk_decile` | §K | |
| 16 | `risk_tier` | §K | |

##### `feature_importance_model_a.csv` / `feature_importance_model_b.csv` — 11 rows each, 1 row per feature

**Population:** n/a — model artifacts. Each model uses 7 numeric features + 4 categorical features (one-hot encoded, then importances summed back to the parent feature via `group_importance()`) = 11 rows.

- **Model A features:** `estimated_delivery_days`, `distance_km`, `order_total_value`, `freight_ratio`, `n_items`, `max_installments`, `is_cross_region` (numeric) + `primary_payment_type`, `category_grp`, `purchase_month`, `purchase_dow` (categorical).
- **Model B features:** `is_late`, `delivery_delay_days`, `order_total_value`, `freight_ratio`, `n_items`, `max_installments`, `n_distinct_sellers` (numeric) + `primary_payment_type`, `category_grp`, `customer_region`, `purchase_month` (categorical).

**⚠ Important framing note:** Model A's #1 feature is `purchase_month` at **52.6%** of total importance — by a wide margin the largest single driver. This reflects **seasonal/operational capacity effects** (e.g. November–December order surges straining carrier capacity), **not** a property of any individual order that a business user can act on directly. `docs/dashboard_build_guide.md` requires an explanatory caption on the Page 7 chart for this feature so it doesn't read as contradicting NB6's order-level narrative (which emphasizes `estimated_delivery_days` and `distance_km` as the actionable, order-level drivers).

**Purpose:** Grouped RandomForest feature importances — feeds the Page 7 feature-importance bar chart for each model.

| # | Column | Glossary | Notes |
|---|---|---|---|
| 1 | `feature` | §A | |
| 2 | `importance` | §K | |
| 3 | `rank` | §K | |
| 4 | `pct_of_total_importance` | §K | |
| 5 | `model` | §A | |

---

#### Drill-Through Detail (cross-page)

##### `orders_detail.csv` — 99,441 rows, 1 row per order

**Population:** **all** orders (the only extract covering the full, unfiltered population — including canceled/unavailable). Use the `order_status`/`is_canceled`/`is_delivered` columns to filter as needed for a given analysis.

**⚠ First-item simplification:** `category`, `category_grp`, `seller_id`, `seller_state`, `seller_state_name`, `seller_region`, `is_cross_region`, and `distance_km` all reflect **only the order's FIRST line item** (`order_item_id=1`). For the 12.9% of orders with multiple items (potentially from different categories/sellers), these columns are a simplification — use `order_items_detail.csv` for full line-item-level category/seller attribution.

**Purpose:** Order-grain detail table for drill-through filtering/inspection from any dashboard page — the widest single extract (36 columns).

| # | Column | Glossary | Notes |
|---|---|---|---|
| 1 | `order_id` | §A | |
| 2 | `customer_unique_id` | §A | |
| 3 | `customer_state` | §L | |
| 4 | `customer_state_name` | §L | |
| 5 | `customer_city` | §L | |
| 6 | `customer_region` | §L | |
| 7 | `order_status` | §A | |
| 8 | `order_purchase_date` | §B | |
| 9 | `purchase_year` | §B | |
| 10 | `purchase_month` | §B | |
| 11 | `purchase_dow` | §B | Monday=0…Sunday=6 (§0.5) |
| 12 | `n_items` | §C | |
| 13 | `n_distinct_sellers` | §C | |
| 14 | `n_distinct_products` | §C | |
| 15 | `order_total_value` | §D | |
| 16 | `items_price_total` | §D | |
| 17 | `freight_value_total` | §D | |
| 18 | `freight_ratio` | §E | |
| 19 | `primary_payment_type` | §A | |
| 20 | `max_installments` | §E | |
| 21 | `estimated_delivery_days` | §F | |
| 22 | `actual_delivery_days` | §F | |
| 23 | `delivery_delay_days` | §F | |
| 24 | `is_late` | §G | |
| 25 | `is_delivered` | §G | |
| 26 | `is_canceled` | §G | |
| 27 | `review_score` | §H | |
| 28 | `has_review` | §H | |
| 29 | `is_negative_review` | §H | |
| 30 | `category` | §A | First item only — see note above |
| 31 | `category_grp` | §A | First item only |
| 32 | `seller_id` | §A | First item only |
| 33 | `seller_state` | §L | First item only |
| 34 | `seller_state_name` | §L | First item only |
| 35 | `seller_region` | §L | First item only |
| 36 | `is_cross_region` | §G | First item only |
| 37 | `distance_km` | §F | First item only |

##### `order_items_detail.csv` — 112,650 rows, 1 row per `(order_id, order_item_id)`

**Population:** **all** line items (all 112,650 rows of `fact_order_items`, including items belonging to canceled/unavailable orders — no filtering applied, unlike the `items_valid` subset used internally by Pages 2/3/6).

**Purpose:** Line-item-grain detail — product/category/seller/price/freight per item, joinable to `orders_detail.csv` via `order_id`. Feeds Page 2/6 drill-throughs where per-item (not per-order-first-item) category/seller attribution matters.

| # | Column | Glossary | Notes |
|---|---|---|---|
| 1 | `order_id` | §A | |
| 2 | `order_item_id` | §A | |
| 3 | `product_id` | §A | |
| 4 | `category` | §A | |
| 5 | `category_grp` | §A | |
| 6 | `seller_id` | §A | |
| 7 | `seller_state` | §L | |
| 8 | `seller_state_name` | §L | |
| 9 | `seller_region` | §L | |
| 10 | `customer_state` | §L | |
| 11 | `customer_state_name` | §L | |
| 12 | `customer_region` | §L | |
| 13 | `order_purchase_date` | §B | |
| 14 | `order_status` | §A | |
| 15 | `price` | §D | |
| 16 | `freight_value` | §D | |
| 17 | `item_total_value` | §D | |

---

## 6. Quick Reference — All 24 Extract Files at a Glance

| File | Page | Grain | Rows |
|---|---|---|---|
| `monthly_kpis.csv` | 1 | month | 24 |
| `seasonality_analysis.csv` | 1 | month | 17 |
| `kpi_summary.csv` | 1 | (single row) | 1 |
| `category_summary.csv` | 2 | category | 74 |
| `category_monthly_mix.csv` | 2 | (month, category_mix) | 220 |
| `top_products.csv` | 2 | product | 50 |
| `geo_customer_state_summary.csv` | 3 | customer_state | 27 |
| `geo_seller_state_summary.csv` | 3 | seller_state | 23 |
| `region_flow_matrix.csv` | 3 | (customer_region, seller_region) | 23 |
| `cycle_time_stages.csv` | 4 | fulfillment stage | 4 |
| `delay_bucket_vs_review.csv` | 4 | delay bucket | 5 |
| `fulfillment_weekly_2018.csv` | 4 | ISO week | 13 |
| `anomaly_state_comparison.csv` | 4 | (customer_state, period) | 48 |
| `customer_segments.csv` | 5 | customer | 92,746 |
| `segment_profile_summary.csv` | 5 | K-Means segment | 4 |
| `rfm_segment_summary.csv` | 5 | RFM segment | 5 |
| `seller_scorecard.csv` | 6 | seller | 3,053 |
| `seller_pareto_deciles.csv` | 6 | revenue decile | 10 |
| `risk_scores_late_delivery.csv` | 7 | order (Model A pop.) | 94,726 |
| `risk_scores_negative_review.csv` | 7 | order (Model B pop.) | 95,824 |
| `feature_importance_model_a.csv` | 7 | feature | 11 |
| `feature_importance_model_b.csv` | 7 | feature | 11 |
| `orders_detail.csv` | drill-through | order | 99,441 |
| `order_items_detail.csv` | drill-through | order item | 112,650 |

