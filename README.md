# End-to-End E-Commerce Retail & Fulfillment Analytics

**An Amazon Retail / Marketplace / Fulfillment-Ops analog, built on the Olist Brazilian E-Commerce dataset.**

A production-style analytics project: a layered SQL warehouse (raw → staging → star-schema
marts) with an automated data-quality framework, a 27-query SQL catalog across four business
domains, six narrated Python notebooks (EDA → time series → geospatial → hypothesis testing →
segmentation → predictive risk modeling), and a 7-page Tableau dashboard built from 24
reproducible extracts.

> **Why Olist, framed as Amazon?** Olist is a multi-seller marketplace where customers order
> items from many 3rd-party sellers, items move through a logistics network against an
> *estimated* delivery date, and customers leave a satisfaction score after delivery. That is
> structurally the same shape as Amazon's Retail + Marketplace + Fulfillment businesses.

---

## Headline findings

- **R$15.74M GMV** across 99,441 orders (AOV **R$160.23**), Sep 2016 – Sep 2018.
- **8.11% of orders arrive late**, but the late rate **varies ~8x by state** (2.9% → 23.9%).
- Orders delayed **4+ days** are only ~5% of reviewed deliveries but drive a collapse in
  satisfaction: average review score falls from **4.30 → 1.73** and the 1-star rate climbs
  from **6.6% → 68.8%** across delay buckets — the single most actionable finding in the
  project.
- **96.9% of customers are one-time buyers** (month-1 retention of just 0.48%, vs. a 20–40%
  industry benchmark), sizing a **~R$4.6M (29% of GMV)** win-back opportunity among lapsed
  high-value customers.
- A Feb–Mar 2018 fulfillment anomaly was root-caused from a monthly KPI down to a weekly,
  state-level spike (late rate **5.2% → 28.99%** in one week) and traced to a national-holiday
  carrier backlog.
- Two RandomForest models flag risk **at order time** (late-delivery AUC = 0.742, catching
  31.9% of eventual late deliveries in the riskiest decile) and **post-delivery**
  (negative-review AUC ≈ 0.745, 56.0% negative-review rate in the riskiest decile vs. a 12.8%
  baseline) — after first demonstrating that a naive random train/test split *overstates*
  performance (AUC = 0.481) due to temporal leakage.

Full narrative, methodology, and business recommendations: **[`docs/CASE_STUDY.md`](docs/CASE_STUDY.md)**.

---

## Architecture

```
data/raw/*.csv (Kaggle)
        |
        v
  raw schema        -- 1 table per source CSV, source-fidelity landing zone
        |
        v
  staging schema    -- typed, deduplicated, dq_* flagged CTAS models
        |
        v
  marts schema      -- star schema: 5 dims + 3 facts, analysis-ready
        |
        +--> sql/analytics/*.sql   -- 27-query SQL catalog (4 business domains)
        |
        +--> notebooks/0{1-6}_*.ipynb  -- EDA, stats, segmentation, ML
        |
        +--> dashboard/extracts/*.csv  -- 24 extracts
                  |
                  v
            Tableau Public  -- 7-page interactive dashboard
```

Every SQL file is written in ANSI/Redshift-compatible SQL, with `DISTKEY`/`SORTKEY` choices
documented inline as comments in `sql/marts/`. The project runs end-to-end on local
PostgreSQL 16, but the schema is designed to map directly onto a real Redshift cluster.

---

## Repository structure

```
.
├── requirements.txt         # Python dependencies (.venv)
├── .env.example              # local Postgres connection template
├── data/
│   └── raw/                  # 9 source CSVs (downloaded via etl/download_data.py, gitignored)
├── etl/                       # Python pipeline scripts (db connection, load, run-sql, DQ, exports)
├── sql/
│   ├── ddl/                   # raw schema DDL
│   ├── staging/                # staging CTAS models
│   ├── marts/                   # star-schema dims + facts (with Redshift DISTKEY/SORTKEY comments)
│   ├── data_quality/             # 39-check DQ suite
│   └── analytics/                  # 27-query SQL catalog, 4 business domains
├── notebooks/                # 6 narrated Jupyter notebooks (EDA -> ML)
├── dashboard/extracts/        # 24 CSV extracts feeding the Tableau workbook
└── docs/
    └── CASE_STUDY.md         # problem -> approach -> findings -> recommendations
```

---

## Tech stack

- **Database:** PostgreSQL 16 (Redshift-compatible SQL — DISTKEY/SORTKEY choices documented in `sql/marts/`)
- **Pipeline:** Python (psycopg2, SQLAlchemy, pandas)
- **Analysis:** pandas, NumPy, SciPy, statsmodels, scikit-learn
- **Visualization:** matplotlib, seaborn, Plotly (notebooks); Tableau Public (dashboard)
- **Notebooks:** Jupyter / nbconvert

---

## Reproducing this project

```bash
# 1. Environment
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
cp .env.example .env   # adjust DB_USER/DB_PASSWORD if your local Postgres needs them

# 2. Database
createdb olist_analytics

# 3. Raw data (Kaggle API credentials required - see etl/download_data.py docstring)
.venv/bin/python etl/download_data.py
.venv/bin/python etl/load_raw_data.py

# 4. Staging -> Marts -> Data Quality
.venv/bin/python etl/run_sql.py sql/staging/01_staging_transform.sql
.venv/bin/python etl/run_sql.py sql/marts/01_dims.sql
.venv/bin/python etl/run_sql.py sql/marts/02_facts.sql
.venv/bin/python etl/run_dq_checks.py     # runs the 39-check DQ suite

# 5. Notebooks (EDA, stats, segmentation, ML) - re-executes in place
.venv/bin/jupyter nbconvert --to notebook --execute --inplace notebooks/*.ipynb

# 6. Dashboard extracts
.venv/bin/python etl/export_dashboard_extracts.py   # writes dashboard/extracts/*.csv
```

The 27 SQL analytics queries in `sql/analytics/` are read-only against the `marts` schema and
can be run individually with `psql` or any SQL client, organized into four business domains:
revenue & growth, customer RFM/cohorts, fulfillment & SLA, and seller marketplace.

---

## Dashboard (7 pages, Tableau Public)

1. Executive Overview
2. Sales & Category Performance
3. Geography
4. Delivery & Fulfillment Operations
5. Customer Segmentation
6. Seller Marketplace
7. Predictive Risk Scoring

Built from the 24 CSVs in `dashboard/extracts/`.

---

## Data source

[Olist Brazilian E-Commerce Public Dataset](https://www.kaggle.com/datasets/olistbr/brazilian-ecommerce)
(Kaggle) — 99,441 orders, 96,096 customers, 3,095 sellers, 74 product categories,
Sep 2016 – Sep 2018. Currency throughout is Brazilian Real (R$); no FX conversion is applied.
