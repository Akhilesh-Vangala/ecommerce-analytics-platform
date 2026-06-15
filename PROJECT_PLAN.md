# Project Plan — E-Commerce Retail & Fulfillment Analytics (Amazon Retail/Ops Analog)

## 1. Framing

Olist operates a multi-seller e-commerce marketplace in Brazil. Structurally this is the
same shape as Amazon's Retail + Marketplace + Fulfillment businesses: customers place
orders containing items from many sellers, items are shipped through a logistics network
with an estimated-vs-actual delivery date, and customers leave a satisfaction score after
delivery. This project treats Olist as an **Amazon Retail/Operations analog**:

- **Amazon Retail lens**: revenue/category performance, customer value segmentation,
  marketplace seller concentration.
- **Amazon Operations lens**: fulfillment network performance — on-time delivery rate,
  carrier vs. last-mile time, SLA (estimated delivery date) breach analysis.
- **Customer Obsession link**: does fulfillment performance (delivery delay) drive
  customer satisfaction (review score)? This is the thread tying Retail and Ops together.

## 2. Architecture — layered warehouse model

```
raw/*.csv  -->  raw schema (landing, 1:1 with source)
             -->  staging schema (typed, cleaned, deduplicated)
             -->  marts schema (star schema: facts + dimensions, analysis-ready)
                  -->  SQL analytics catalog (CTEs/window functions, by domain)
                  -->  Python EDA/statistics/ML
                  -->  Tableau extracts / dashboard
```

- **raw**: one table per source CSV, types loosely matched to source, no constraints —
  preserves source fidelity for lineage/debugging.
- **staging**: one model per raw table — casts types, trims/normalizes text, deduplicates,
  flags data quality issues. Built with `CREATE TABLE AS SELECT` (CTAS), dbt-model style.
- **marts**: star schema —
  - `dim_date`, `dim_customer` (deduped to `customer_unique_id` grain — the actual person),
    `dim_product`, `dim_seller`, `dim_geography`
  - `fact_orders` (order grain — delivery metrics, payment totals, review score, flags)
  - `fact_order_items` (line-item grain — price, freight, product, seller)

DDL includes Redshift `DISTKEY`/`SORTKEY` annotations (as SQL comments + a documented
Redshift variant) even though the working DB is local Postgres — see
`redshift/DEPLOYMENT.md` for the optional real-Redshift deployment path.

## 3. Data quality framework

`sql/data_quality/` — automated checks run after each layer build:
- Row-count reconciliation (raw -> staging -> marts)
- Null-rate checks on key business columns
- Duplicate primary key checks
- Referential integrity (orphaned FKs across facts/dims)
- Valid value-range checks (dates, prices, review scores 1-5)
- Logical consistency (e.g., delivery date >= purchase date)

Output: `docs/data_quality_report.md` with pass/fail counts per check.

## 4. SQL analytics catalog (`sql/analytics/`)

Each file = one business domain, multiple queries, each with a business-question header
comment, using CTEs + window functions:

1. `01_revenue_growth.sql` — MoM/YoY revenue & order growth, category mix shift, running
   totals, top-N products/categories per period (RANK/ROW_NUMBER)
2. `02_customer_rfm_cohorts.sql` — RFM segmentation, cohort retention curves, repeat
   purchase rate, simple CLV estimate
3. `03_fulfillment_ops.sql` — on-time delivery rate by state/category/seller, carrier vs.
   last-mile time decomposition, SLA breach trend over time
4. `04_seller_marketplace.sql` — seller concentration (Pareto/80-20), seller scorecards,
   seller performance vs. delivery/satisfaction outcomes

## 5. Python EDA + statistics (`notebooks/`)

`01_eda_and_statistics.ipynb` (tier-1, narrated):
- Data profiling (missingness, cardinality, distributions, outliers)
- Univariate -> bivariate -> multivariate analysis with written interpretation
- Time series decomposition (trend/seasonality) of orders & revenue
- Geospatial analysis (state-level choropleth: revenue, delivery time, satisfaction)
- Hypothesis testing: delivery delay vs. review score (assumption checks + test choice),
  category/region effects
- Customer segmentation: RFM + K-means (elbow/silhouette validation), segment profiles
- Predictive modeling (interpretation-focused): logistic regression for late-delivery
  risk and low-review risk — coefficients, ROC/AUC, confusion matrix

## 6. Dashboard (Tableau Public)

`dashboard/extracts/` — clean, pre-aggregated CSV/view extracts for each dashboard page:
Executive KPI summary, Sales & Category, Geography map, Delivery & Satisfaction,
Customer Segments, Seller Performance.

## 7. Documentation deliverables (`docs/`)

- `data_dictionary.md` — every column, source, type, definition
- `sql_query_catalog.md` — business question -> query -> answer, for every analytics query
- `data_quality_report.md`
- `CASE_STUDY.md` — problem -> approach -> findings -> recommendations -> projected impact

## 8. Engineering hygiene

- `.venv/` local virtualenv, `requirements.txt`
- `.env` / `.env.example` connection settings via `etl/db.py` (local Postgres now,
  Redshift-ready — see `redshift/DEPLOYMENT.md`)
- `etl/` idempotent Python load scripts with logging
- git repo with incremental commits per layer/milestone

## 9. Build order (this session onward)

1. Raw schema DDL + ETL load -> verify row counts
2. Staging layer (CTAS, cleaning/dedup)
3. Marts layer (star schema CTAS)
4. Data quality checks + report
5. SQL analytics catalog (4 domains)
6. Python EDA notebook (profiling -> stats -> segmentation -> modeling)
7. Tableau extracts
8. Documentation (data dictionary, query catalog, case study)
9. Redshift deployment notes
10. Resume bullets
