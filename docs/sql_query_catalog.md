# SQL Query Catalog

This catalog documents every analytics query in `sql/analytics/*.sql` (27 queries across 4 business domains): the **business question** it answers, the **full SQL**, the **actual result** (run against the local PostgreSQL 16 warehouse, `olist_analytics`, on 2026-06-14), and the **key finding** — written the way an analyst would hand off a query result to a stakeholder.

## 0. How to Read This Document

### 0.1 Scope and source of truth

The SQL itself (`sql/analytics/01_revenue_growth.sql` … `04_seller_marketplace.sql`) is the source of truth and contains additional inline methodology notes (why a given window/threshold was chosen, edge cases, etc.). This catalog surfaces the **business question**, a clean copy of the **query**, the **result set**, and the **headline finding** for each — so a reviewer can scan all 27 analyses end-to-end without opening four separate files. Large result sets (>15 rows) are shown as a representative top/bottom slice with a pointer to the full CSV (either re-runnable from the SQL, or already materialized in `dashboard/extracts/`).

### 0.2 Conventions used throughout (see `docs/data_dictionary.md` §0 for full detail)

| Convention | Detail |
|---|---|
| **Order population** | Unless stated otherwise, queries filter `order_status NOT IN ('canceled','unavailable')` — the "Valid orders" population (98,207 of 99,441). Canceled/unavailable orders never generated fulfilled revenue and would distort GMV/AOV. |
| **Delivered population** | Fulfillment queries (Domain 3) use `is_delivered AND NOT dq_delivered_missing_date` (96,470 orders) — see data dictionary §0.3. |
| **DQ-flag exclusions** | `dq_carrier_before_approval` (1.37% of orders) and `dq_delivered_before_carrier` (0.02%) are timestamp anomalies excluded from the affected *stage's* timing average only (per `docs/data_quality_report.md`). |
| **Currency** | All monetary values are Brazilian Real (BRL, R$), undeflated (no inflation adjustment across the 2016-2018 window). |
| **Analysis window** | Trend queries use **2017-01 to 2018-08** (the first full, comparable 20-month window) — 2016 has only 296 orders (platform pilot) and Sep-Oct 2018 has only 20 orders (extract cutoff). |
| **Redshift portability** | Every query uses only ANSI/Redshift-supported constructs (`DATE_TRUNC`, `EXTRACT`, `NTILE`, `RANK`, `LAG`, `PERCENTILE_CONT`, window frames). No Postgres-only syntax. The underlying `marts.*` tables carry `DISTKEY`/`SORTKEY`/`DISTSTYLE` recommendations as comments in `sql/marts/01_dims.sql` / `02_facts.sql` for a future Redshift migration. |

### 0.3 Query index

| # | Title | Domain | Result rows |
|---|---|---|---|
| [Q1.1](#q11-monthly-gmv--order-volume-trend-with-mom-growth) | Monthly GMV & order volume trend with MoM growth | Revenue & Growth | 20 |
| [Q1.2](#q12-cumulative-gmv-and-3-month-rolling-average) | Cumulative GMV and 3-month rolling average | Revenue & Growth | 20 |
| [Q1.3](#q13-year-over-year-comparison-jan-aug-2017-vs-jan-aug-2018) | Year-over-year comparison, Jan-Aug 2017 vs Jan-Aug 2018 | Revenue & Growth | 8 |
| [Q1.4](#q14-revenue-concentration-pareto-by-product-category) | Revenue concentration (Pareto) by product category | Revenue & Growth | 74 |
| [Q1.5](#q15-category-mix-shift-jan-aug-2017-vs-jan-aug-2018) | Category mix shift, Jan-Aug 2017 vs Jan-Aug 2018 | Revenue & Growth | 41 |
| [Q1.6](#q16-top-3-products-by-revenue-within-the-top-5-categories) | Top-3 products by revenue within the top-5 categories | Revenue & Growth | 15 |
| [Q1.7](#q17-seasonality---de-trended-monthly-spike-detection) | Seasonality — de-trended monthly spike detection | Revenue & Growth | 19 |
| [Q2.1](#q21-rfm-segmentation-recency--monetary-quintiles) | RFM segmentation (Recency × Monetary quintiles) | Customer RFM & Cohorts | 25 |
| [Q2.2](#q22-repeat-purchase-rate-and-time-to-second-order) | Repeat-purchase rate and time-to-second-order | Customer RFM & Cohorts | 1 |
| [Q2.3](#q23-acquisition-cohort-retention-curve-months-0-6) | Acquisition-cohort retention curve, months 0-6 | Customer RFM & Cohorts | 98 |
| [Q2.4](#q24-new-vs-returning-customer-share-of-orders--gmv) | New vs. returning-customer share of orders & GMV | Customer RFM & Cohorts | 20 |
| [Q2.5](#q25-customer-ltv-distribution-and-revenue-concentration-by-decile) | Customer LTV distribution and revenue concentration by decile | Customer RFM & Cohorts | 10 |
| [Q2.6](#q26-customer-geography---order-volume-gmv-aov-by-state) | Customer geography — order volume, GMV, AOV by state | Customer RFM & Cohorts | 27 |
| [Q3.1](#q31-order-status-funnel) | Order status funnel | Fulfillment & Ops | 8 |
| [Q3.2](#q32-monthly-on-time-delivery-rate-otd--cycle-time) | Monthly on-time delivery rate (OTD) & cycle time | Fulfillment & Ops | 20 |
| [Q3.3](#q33-fulfillment-cycle-time-stage-breakdown) | Fulfillment cycle-time stage breakdown | Fulfillment & Ops | 4 |
| [Q3.4](#q34-on-time-delivery-rate-by-customer-state) | On-time delivery rate by customer state | Fulfillment & Ops | 27 |
| [Q3.5](#q35-delivery-delay-bucket-vs-review-score) | Delivery-delay bucket vs. review score | Fulfillment & Ops | 5 |
| [Q3.6](#q36-estimated-delivery-date-accuracy-distribution) | Estimated-delivery-date accuracy distribution | Fulfillment & Ops | 5 |
| [Q3.7](#q37-did-the-nov-2017-demand-spike-strain-fulfillment) | Did the Nov-2017 demand spike strain fulfillment? | Fulfillment & Ops | 5 |
| [Q3.8](#q38-anomaly-drill-down---the-feb-mar-2018-otd-collapse) | Anomaly drill-down — the Feb-Mar 2018 OTD collapse | Fulfillment & Ops | 13 |
| [Q4.1](#q41-seller-revenue-concentration-pareto-by-decile) | Seller revenue concentration (Pareto) by decile | Seller & Marketplace | 10 |
| [Q4.2](#q42-top-20-sellers-by-revenue---performance-scorecard) | Top-20 sellers by revenue — performance scorecard | Seller & Marketplace | 20 |
| [Q4.3](#q43-seller-acquisition--activity-trend) | Seller acquisition & activity trend | Seller & Marketplace | 20 |
| [Q4.4](#q44-same-state-vs-cross-state-freight-cost--transit-time) | Same-state vs. cross-state freight cost & transit time | Seller & Marketplace | 2 |
| [Q4.5](#q45-seller-supply-concentration-by-state) | Seller supply concentration by state | Seller & Marketplace | 23 |
| [Q4.6](#q46-marketplace-concentration-risk-hhi-in-top-5-categories) | Marketplace concentration risk (HHI) in top-5 categories | Seller & Marketplace | 5 |

---

## Domain 1: Revenue & Growth
*(`sql/analytics/01_revenue_growth.sql`)* — the Amazon Retail / merchandising lens: is the marketplace growing, where does revenue concentrate, and is there a recurring seasonal pattern Operations needs to plan around?

### Q1.1: Monthly GMV & order volume trend with MoM growth

**Business question:** Is the marketplace growing, and how volatile is month-to-month growth?

```sql
WITH monthly AS (
    SELECT
        DATE_TRUNC('month', order_purchase_date)::date AS month,
        COUNT(DISTINCT order_id)                       AS n_orders,
        SUM(order_total_value)                         AS gmv
    FROM marts.fact_orders
    WHERE order_status NOT IN ('canceled', 'unavailable')
      AND order_purchase_date BETWEEN '2017-01-01' AND '2018-08-31'
    GROUP BY 1
)
SELECT
    month,
    n_orders,
    ROUND(gmv::numeric, 2) AS gmv,
    ROUND(gmv::numeric, 2) - ROUND(LAG(gmv) OVER (ORDER BY month)::numeric, 2) AS gmv_mom_change,
    ROUND(100.0 * (gmv - LAG(gmv) OVER (ORDER BY month)) / LAG(gmv) OVER (ORDER BY month), 1) AS gmv_mom_pct,
    ROUND(100.0 * (n_orders - LAG(n_orders) OVER (ORDER BY month)) / LAG(n_orders) OVER (ORDER BY month), 1) AS orders_mom_pct
FROM monthly
ORDER BY month;
```

**Result** (20 rows, 2017-01 … 2018-08):

| month | n_orders | gmv | gmv_mom_change | gmv_mom_pct | orders_mom_pct |
|---|---|---|---|---|---|
| 2017-01 | 787 | 136,943.46 | — | — | — |
| 2017-02 | 1,718 | 283,561.69 | +146,618.23 | +107.1% | +118.3% |
| 2017-03 | 2,617 | 425,617.96 | +142,056.27 | +50.1% | +52.3% |
| 2017-04 | 2,377 | 405,848.61 | -19,769.35 | -4.6% | -9.2% |
| 2017-05 | 3,640 | 582,710.83 | +176,862.22 | +43.6% | +53.1% |
| 2017-06 | 3,205 | 499,652.24 | -83,058.59 | -14.3% | -12.0% |
| 2017-07 | 3,946 | 578,753.73 | +79,101.49 | +15.8% | +23.1% |
| 2017-08 | 4,272 | 661,903.52 | +83,149.79 | +14.4% | +8.3% |
| 2017-09 | 4,227 | 717,102.72 | +55,199.20 | +8.3% | -1.1% |
| 2017-10 | 4,547 | 764,756.03 | +47,653.31 | +6.6% | +7.6% |
| 2017-11 | 7,423 | 1,172,191.68 | +407,435.65 | +53.3% | +63.3% |
| 2017-12 | 5,620 | 861,526.77 | -310,664.91 | -26.5% | -24.3% |
| 2018-01 | 7,187 | 1,101,920.01 | +240,393.24 | +27.9% | +27.9% |
| 2018-02 | 6,625 | 979,486.16 | -122,433.85 | -11.1% | -7.8% |
| 2018-03 | 7,168 | 1,152,656.99 | +173,170.83 | +17.7% | +8.2% |
| 2018-04 | 6,919 | 1,156,248.89 | +3,591.90 | +0.3% | -3.5% |
| 2018-05 | 6,833 | 1,145,686.46 | -10,562.43 | -0.9% | -1.2% |
| 2018-06 | 6,145 | 1,020,381.90 | -125,304.56 | -10.9% | -10.1% |
| 2018-07 | 6,233 | 1,039,783.58 | +19,401.68 | +1.9% | +1.4% |
| 2018-08 | 6,421 | 996,973.51 | -42,810.07 | -4.1% | +3.0% |

**Key finding:** GMV grew from R$136.9K (Jan-2017) to a peak of R$1.17M (Nov-2017, Black Friday) and has plateaued around **R$1.0-1.16M/month since Feb-2018** — i.e. the explosive 2017 hyper-growth phase has matured into a flatter ~R$1.0-1.2M/month plateau through Aug-2018. MoM growth is extremely volatile in 2017 (swings of ±50-100%, typical of a young marketplace) but stabilizes to single-digit swings from mid-2018. The two largest single-month jumps — Nov-2017 (+53.3% orders / Black Friday) and Jan-2018 (+27.9%, the post-Black-Friday-recovery/New Year rebound) — are the two seasonal events that recur in Q1.7.

---

### Q1.2: Cumulative GMV and 3-month rolling average

**Business question:** What is the underlying growth trend once monthly noise/seasonality is smoothed out?

```sql
WITH monthly AS (
    SELECT
        DATE_TRUNC('month', order_purchase_date)::date AS month,
        SUM(order_total_value) AS gmv
    FROM marts.fact_orders
    WHERE order_status NOT IN ('canceled', 'unavailable')
      AND order_purchase_date BETWEEN '2017-01-01' AND '2018-08-31'
    GROUP BY 1
)
SELECT
    month,
    ROUND(gmv::numeric, 2) AS gmv,
    ROUND(SUM(gmv) OVER (ORDER BY month)::numeric, 2) AS cumulative_gmv,
    ROUND(AVG(gmv) OVER (ORDER BY month ROWS BETWEEN 2 PRECEDING AND CURRENT ROW)::numeric, 2) AS gmv_3mo_moving_avg
FROM monthly
ORDER BY month;
```

**Result** (20 rows; first/last 6 shown, full 20 in `/tmp/catalog_results/Q1.2.csv` — re-runnable):

| month | gmv | cumulative_gmv | gmv_3mo_moving_avg |
|---|---|---|---|
| 2017-01 | 136,943.46 | 136,943.46 | 136,943.46 |
| 2017-02 | 283,561.69 | 420,505.15 | 210,252.58 |
| 2017-03 | 425,617.96 | 846,123.11 | 282,041.04 |
| 2017-04 | 405,848.61 | 1,251,971.72 | 371,676.09 |
| 2017-05 | 582,710.83 | 1,834,682.55 | 471,392.47 |
| 2017-06 | 499,652.24 | 2,334,334.79 | 496,070.56 |
| … | … | … | … |
| 2018-03 | 1,152,656.99 | 10,324,632.40 | 1,078,021.05 |
| 2018-04 | 1,156,248.89 | 11,480,881.29 | 1,096,130.68 |
| 2018-05 | 1,145,686.46 | 12,626,567.75 | 1,151,530.78 |
| 2018-06 | 1,020,381.90 | 13,646,949.65 | 1,107,439.08 |
| 2018-07 | 1,039,783.58 | 14,686,733.23 | 1,068,617.31 |
| 2018-08 | 996,973.51 | 15,683,706.74 | 1,019,046.33 |

**Key finding:** Total GMV across the 20-month window is **R$15.68M**. The 3-month moving average rose almost monotonically through Nov-2017 (peaking at R$884.7K trailing-avg), continued climbing through a second peak around Apr-2018 (R$1.15M trailing-avg), and has been gently **declining since** (R$1.02M by Aug-2018) — confirming the plateau/early-deceleration read from Q1.1 with the seasonal noise removed. For a senior stakeholder: growth has not reversed, but the **rate of growth has gone from explosive (2017) to roughly flat-to-slightly-declining (2018 H1)** — exactly the inflection point where an Amazon-style BA would be asked "what's the next growth lever" (Domain 2's answer: it isn't repeat purchase, which is still <4% of monthly orders).

---

### Q1.3: Year-over-year comparison, Jan-Aug 2017 vs Jan-Aug 2018

**Business question:** How much did the business grow year-over-year on a like-for-like basis?

```sql
WITH monthly AS (
    SELECT
        EXTRACT(YEAR FROM order_purchase_date)::int  AS yr,
        EXTRACT(MONTH FROM order_purchase_date)::int AS mo,
        COUNT(DISTINCT order_id) AS n_orders,
        SUM(order_total_value)   AS gmv
    FROM marts.fact_orders
    WHERE order_status NOT IN ('canceled', 'unavailable')
      AND EXTRACT(MONTH FROM order_purchase_date) BETWEEN 1 AND 8
      AND EXTRACT(YEAR FROM order_purchase_date) IN (2017, 2018)
    GROUP BY 1, 2
)
SELECT
    mo AS month_number,
    SUM(CASE WHEN yr = 2017 THEN n_orders END) AS orders_2017,
    SUM(CASE WHEN yr = 2018 THEN n_orders END) AS orders_2018,
    ROUND(SUM(CASE WHEN yr = 2017 THEN gmv END)::numeric, 2) AS gmv_2017,
    ROUND(SUM(CASE WHEN yr = 2018 THEN gmv END)::numeric, 2) AS gmv_2018,
    ROUND(100.0 * (SUM(CASE WHEN yr = 2018 THEN gmv END) - SUM(CASE WHEN yr = 2017 THEN gmv END))
          / SUM(CASE WHEN yr = 2017 THEN gmv END), 1) AS gmv_yoy_pct
FROM monthly
GROUP BY mo
ORDER BY mo;
```

**Result** (8 rows):

| month_number | orders_2017 | orders_2018 | gmv_2017 | gmv_2018 | gmv_yoy_pct |
|---|---|---|---|---|---|
| 1 (Jan) | 787 | 7,187 | 136,943.46 | 1,101,920.01 | **+704.7%** |
| 2 (Feb) | 1,718 | 6,625 | 283,561.69 | 979,486.16 | +245.4% |
| 3 (Mar) | 2,617 | 7,168 | 425,617.96 | 1,152,656.99 | +170.8% |
| 4 (Apr) | 2,377 | 6,919 | 405,848.61 | 1,156,248.89 | +184.9% |
| 5 (May) | 3,640 | 6,833 | 582,710.83 | 1,145,686.46 | +96.6% |
| 6 (Jun) | 3,205 | 6,145 | 499,652.24 | 1,020,381.90 | +104.2% |
| 7 (Jul) | 3,946 | 6,233 | 578,753.73 | 1,039,783.58 | +79.7% |
| 8 (Aug) | 4,272 | 6,421 | 661,903.52 | 996,973.51 | +50.6% |

**Key finding:** Every month of 2018 vastly outperformed its 2017 counterpart — but the YoY growth rate **decelerates monotonically from +704.7% (Jan) to +50.6% (Aug)**, because Jan-2017 was still in the platform's earliest ramp-up (only 787 orders) while Aug-2017 was already a relatively mature month (4,272 orders). This is the YoY mirror of the Q1.2 plateau: **2018's growth is real but is converging toward 2017's already-higher base**, not accelerating. An Amazon-style read: the eye-catching "+700% YoY" headline number for January is a base-rate artifact, not a sign January 2018 itself was extraordinary (it wasn't — Jan-2018's 7,187 orders is in line with the rest of H1-2018). The August figure (+50.6%) is the more representative "steady-state" YoY growth rate for this business today.

---

### Q1.4: Revenue concentration (Pareto) by product category

**Business question:** How concentrated is revenue across categories — does a small set of categories drive most of GMV?

```sql
WITH cat_rev AS (
    SELECT
        dp.product_category_name_english AS category,
        COUNT(*)        AS n_items_sold,
        SUM(fi.price)   AS revenue
    FROM marts.fact_order_items fi
    JOIN marts.dim_product dp ON dp.product_id = fi.product_id
    GROUP BY 1
)
SELECT
    category,
    n_items_sold,
    ROUND(revenue::numeric, 2) AS revenue,
    ROUND(100.0 * revenue / SUM(revenue) OVER (), 2) AS pct_of_total_revenue,
    ROUND(100.0 * SUM(revenue) OVER (ORDER BY revenue DESC) / SUM(revenue) OVER (), 2) AS cumulative_pct_of_revenue,
    RANK() OVER (ORDER BY revenue DESC) AS revenue_rank
FROM cat_rev
ORDER BY revenue DESC;
```

**Result** (74 categories total, R$13.59M item revenue; top 12 shown — full breakdown in `dashboard/extracts/category_summary.csv`):

| rank | category | n_items_sold | revenue | % of total | cumulative % |
|---|---|---|---|---|---|
| 1 | health_beauty | 9,670 | 1,258,681.34 | 9.26% | 9.26% |
| 2 | watches_gifts | 5,991 | 1,205,005.68 | 8.87% | 18.13% |
| 3 | bed_bath_table | 11,115 | 1,036,988.68 | 7.63% | 25.76% |
| 4 | sports_leisure | 8,641 | 988,048.97 | 7.27% | 33.03% |
| 5 | computers_accessories | 7,827 | 911,954.32 | 6.71% | 39.74% |
| 6 | furniture_decor | 8,334 | 729,762.49 | 5.37% | 45.10% |
| 7 | cool_stuff | 3,796 | 635,290.85 | 4.67% | 49.78% |
| 8 | housewares | 6,964 | 632,248.66 | 4.65% | 54.43% |
| 9 | auto | 4,235 | 592,720.11 | 4.36% | 58.79% |
| 10 | garden_tools | 4,347 | 485,256.46 | 3.57% | 62.36% |
| 11 | toys | 4,117 | 483,946.60 | 3.56% | 65.92% |
| 12 | baby | 3,065 | 411,764.89 | 3.03% | 68.95% |
| … | (62 more categories) | | | | → 100.00% |
| 73 | fashion_childrens_clothes | 8 | 569.85 | 0.00% | 99.99% |
| 74 | security_and_services | 2 | 283.29 | 0.00% | 100.00% |

**Key finding:** Revenue concentration is **moderate, not extreme** — the top 10 categories account for **62.36%** of GMV and the top 3 ("health & beauty," "watches & gifts," "bed/bath/table") for ~26%, but no single category dominates (the #1 category is just 9.26% of revenue). This is a healthier risk profile than the seller-side concentration in Domain 4 (where the top 10% of *sellers* drive 67.5% of revenue — Q4.1): **category mix is diversified, but seller supply within those categories is not**. The long tail is real — 64 of 74 categories (86%) combine for under 32% of revenue, with the bottom ~15 categories each contributing <0.1%.

---

### Q1.5: Category mix shift, Jan-Aug 2017 vs Jan-Aug 2018

**Business question:** Beyond overall growth, which categories are growing faster/slower than the marketplace as a whole?

```sql
WITH cat_period AS (
    SELECT
        dp.product_category_name_english AS category,
        EXTRACT(YEAR FROM fi.order_purchase_date)::int AS yr,
        SUM(fi.price) AS revenue
    FROM marts.fact_order_items fi
    JOIN marts.dim_product dp ON dp.product_id = fi.product_id
    WHERE EXTRACT(MONTH FROM fi.order_purchase_date) BETWEEN 1 AND 8
      AND EXTRACT(YEAR FROM fi.order_purchase_date) IN (2017, 2018)
    GROUP BY 1, 2
),
shares AS (
    SELECT
        category, yr, revenue,
        revenue / SUM(revenue) OVER (PARTITION BY yr) AS share_of_year
    FROM cat_period
)
SELECT
    s17.category,
    ROUND(s17.revenue::numeric, 2)        AS revenue_2017,
    ROUND(s18.revenue::numeric, 2)        AS revenue_2018,
    ROUND(100.0 * s17.share_of_year, 2)   AS pct_share_2017,
    ROUND(100.0 * s18.share_of_year, 2)   AS pct_share_2018,
    ROUND(100.0 * (s18.share_of_year - s17.share_of_year), 2) AS share_pt_change,
    ROUND(100.0 * (s18.revenue - s17.revenue) / s17.revenue, 1) AS revenue_growth_pct
FROM shares s17
JOIN shares s18 ON s18.category = s17.category AND s17.yr = 2017 AND s18.yr = 2018
WHERE s17.revenue > 5000  -- ignore long-tail categories with too little volume for a stable %
ORDER BY share_pt_change DESC;
```

**Result** (41 categories with >R$5K revenue in Jan-Aug 2017; top 8 gainers and top 5 decliners shown by share-point change — full 41-row table in `/tmp/catalog_results/Q1.5.csv`):

**Top gainers (gaining share of GMV):**

| category | revenue_2017 | revenue_2018 | share_2017 | share_2018 | share_pt_change | revenue_growth_pct |
|---|---|---|---|---|---|---|
| watches_gifts | 210,247.18 | 708,850.94 | 6.75% | 9.60% | **+2.84pp** | +237.2% |
| health_beauty | 247,917.28 | 772,238.15 | 7.96% | 10.46% | **+2.49pp** | +211.5% |
| baby | 70,788.37 | 256,800.70 | 2.27% | 3.48% | +1.20pp | +262.8% |
| housewares | 133,986.33 | 399,888.10 | 4.30% | 5.41% | +1.11pp | +198.5% |
| home_appliances_2 | 12,788.82 | 89,252.86 | 0.41% | 1.21% | +0.80pp | +597.9% |
| stationery | 37,414.56 | 136,360.31 | 1.20% | 1.85% | +0.64pp | +264.5% |
| home_construction | 6,721.45 | 59,135.67 | 0.22% | 0.80% | +0.58pp | +779.8% |
| telephony | 61,228.74 | 180,293.31 | 1.97% | 2.44% | +0.47pp | +194.5% |

**Top decliners (losing share of GMV):**

| category | revenue_2017 | revenue_2018 | share_2017 | share_2018 | share_pt_change | revenue_growth_pct |
|---|---|---|---|---|---|---|
| **cool_stuff** | 215,193.52 | 240,559.20 | 6.91% | 3.26% | **-3.66pp** | +11.8% |
| bed_bath_table | 259,850.84 | 538,069.26 | 8.35% | 7.29% | -1.06pp | +107.1% |
| perfumery | 123,548.27 | 178,462.17 | 3.97% | 2.42% | -1.55pp | +44.4% |
| toys | 120,428.22 | 171,506.03 | 3.87% | 2.32% | -1.55pp | +42.4% |
| garden_tools | 146,734.87 | 215,013.87 | 4.71% | 2.91% | -1.80pp | +46.5% |

**Key finding:** Every one of these 41 categories grew in **absolute** revenue (the marketplace itself grew ~3x over this period — Q1.3), so "decliner" here means *growing slower than the marketplace average*, not shrinking. The standout: **`cool_stuff`** still grew +11.8% in absolute terms but lost **3.66 percentage points** of category share — the single largest share shift of any category, and a candidate for a "why is this category underperforming the platform average" merchandising review. The biggest share **gainers** — `watches_gifts` and `health_beauty` — are also the #2 and #1 categories by absolute revenue (Q1.4), meaning the marketplace's overall growth is increasingly concentrated in its already-largest categories (a "winners keep winning" dynamic). `home_construction` and `home_appliances_2` show the highest *relative* growth rates (+779.8% and +597.9%) but from a small base, so their absolute share gain (+0.58pp / +0.80pp) is modest — worth watching as potential emerging categories but not yet strategically significant.

---

### Q1.6: Top-3 products by revenue within the top-5 categories

**Business question:** Within our highest-revenue categories, which specific products should merchandising/inventory teams prioritize?

```sql
WITH top_categories AS (
    SELECT dp.product_category_name_english AS category
    FROM marts.fact_order_items fi
    JOIN marts.dim_product dp ON dp.product_id = fi.product_id
    GROUP BY 1
    ORDER BY SUM(fi.price) DESC
    LIMIT 5
),
product_rev AS (
    SELECT
        dp.product_category_name_english AS category,
        fi.product_id,
        COUNT(*)      AS n_sold,
        SUM(fi.price) AS revenue
    FROM marts.fact_order_items fi
    JOIN marts.dim_product dp ON dp.product_id = fi.product_id
    WHERE dp.product_category_name_english IN (SELECT category FROM top_categories)
    GROUP BY 1, 2
),
ranked AS (
    SELECT
        category, product_id, n_sold, revenue,
        RANK() OVER (PARTITION BY category ORDER BY revenue DESC) AS rank_in_category
    FROM product_rev
)
SELECT category, rank_in_category, product_id, n_sold, ROUND(revenue::numeric, 2) AS revenue
FROM ranked
WHERE rank_in_category <= 3
ORDER BY category, rank_in_category;
```

**Result** (15 rows = 5 categories × top 3):

| category | rank | product_id | n_sold | revenue |
|---|---|---|---|---|
| bed_bath_table | 1 | 99a4788cb24856965c36a24e339b6058 | 488 | 43,025.56 |
| bed_bath_table | 2 | f1c7f353075ce59d8a6f3cf58f419c9c | 154 | 29,997.36 |
| bed_bath_table | 3 | 84f456958365164420cfc80fbe4c7fab | 111 | 10,304.96 |
| computers_accessories | 1 | d1c427060a0f73f6b889a5c7c61f2ac4 | 343 | 47,214.51 |
| computers_accessories | 2 | 3dd2a17168ec895c781a9191c1e95ad7 | 274 | 41,082.60 |
| computers_accessories | 3 | e53e557d5a159f5aa2c5e995dfdf244b | 183 | 15,439.25 |
| health_beauty | 1 | bb50f2e236e5eea0100680137654686c | 195 | 63,885.00 |
| health_beauty | 2 | 6cdd53843498f92890544667809f1595 | 156 | 54,730.20 |
| health_beauty | 3 | 2b4609f8948be18874494203496bc318 | 260 | 22,717.22 |
| sports_leisure | 1 | b4436da747c3a53ab07ac0e71de17dcd | 6 | 9,594.00 |
| sports_leisure | 2 | 0bbdc963004d9b2fd3427ee3c5ae3608 | 30 | 9,070.00 |
| sports_leisure | 3 | e44f675b60b3a3a2453ec36421e06f0f | 84 | 8,949.10 |
| watches_gifts | 1 | 53b36df67ebb7c41585e8d54d6772e08 | 323 | 37,683.42 |
| watches_gifts | 2 | e0d64dcfaa3b6db5c54ca298ae101d05 | 194 | 31,786.82 |
| watches_gifts | 3 | d285360f29ac7fd97640bf0baef03de0 | 123 | 31,623.81 |

**Key finding:** The #1 product in `health_beauty` (`bb50f2e2…`) generates **R$63,885** from just 195 units — an average selling price of ~R$328, an order of magnitude above the category's overall pattern (most top sellers move 100s of units at lower price points). By contrast, `sports_leisure`'s top product (`b4436da7…`) sells only 6 units for R$9,594 — i.e., **R$1,599/unit**, clearly a premium/big-ticket item (e.g. exercise equipment) whose revenue contribution comes from price, not volume. This distinction matters operationally: high-unit-count products (e.g. `computers_accessories` #1 at 343 units) are inventory/logistics priorities, while low-unit high-price products are merchandising/marketing priorities (each sale matters disproportionately, and a single bad review has outsized impact on that product's reputation). All 15 products are candidates for the "feature this on the category landing page" placement an Amazon Retail merchandising analyst would recommend.

---

### Q1.7: Seasonality — de-trended monthly spike detection

**Business question:** Is there a recurring seasonal pattern, and how large is it relative to what the recent trend would predict?

```sql
WITH monthly AS (
    SELECT
        DATE_TRUNC('month', order_purchase_date)::date AS month,
        SUM(order_total_value) AS gmv
    FROM marts.fact_orders
    WHERE order_status NOT IN ('canceled', 'unavailable')
      AND order_purchase_date BETWEEN '2017-01-01' AND '2018-08-31'
    GROUP BY 1
),
trend AS (
    SELECT
        month,
        gmv,
        AVG(gmv) OVER (ORDER BY month ROWS BETWEEN 3 PRECEDING AND 1 PRECEDING) AS trailing_3mo_avg
    FROM monthly
)
SELECT
    month,
    ROUND(gmv::numeric, 2) AS gmv,
    ROUND(trailing_3mo_avg::numeric, 2) AS trailing_3mo_avg,
    ROUND((100.0 * (gmv - trailing_3mo_avg) / trailing_3mo_avg)::numeric, 1) AS pct_above_trailing_avg,
    (gmv > 1.3 * trailing_3mo_avg) AS is_seasonal_spike
FROM trend
WHERE trailing_3mo_avg IS NOT NULL  -- Jan-2017 has no trailing months
ORDER BY month;
```

**Methodology note:** a naive "z-score vs. the full-period mean/stddev" approach was tried first and flagged **zero** months — the strong 2017→2018 growth trend inflates the overall stddev enough to mask the Nov-2017 spike (z=1.20, below the |z|>2 threshold). The fix: de-trend by comparing each month to the **average of its own trailing 3 months** rather than a single global average — the correct general pattern for seasonality detection on a fast-growing series.

**Result** (19 rows, 2017-02 … 2018-08; spikes in **bold**):

| month | gmv | trailing_3mo_avg | pct_above_trailing_avg | is_seasonal_spike |
|---|---|---|---|---|
| **2017-02** | 283,561.69 | 136,943.46 | +107.1% | **True** |
| **2017-03** | 425,617.96 | 210,252.58 | +102.4% | **True** |
| **2017-04** | 405,848.61 | 282,041.04 | +43.9% | **True** |
| **2017-05** | 582,710.83 | 371,676.09 | +56.8% | **True** |
| 2017-06 | 499,652.24 | 471,392.47 | +6.0% | False |
| 2017-07 | 578,753.73 | 496,070.56 | +16.7% | False |
| 2017-08 | 661,903.52 | 553,705.60 | +19.5% | False |
| 2017-09 | 717,102.72 | 580,103.16 | +23.6% | False |
| 2017-10 | 764,756.03 | 652,586.66 | +17.2% | False |
| **2017-11** | 1,172,191.68 | 714,587.42 | **+64.0%** | **True** |
| 2017-12 | 861,526.77 | 884,683.48 | -2.6% | False |
| 2018-01 | 1,101,920.01 | 932,824.83 | +18.1% | False |
| 2018-02 | 979,486.16 | 1,045,212.82 | -6.3% | False |
| 2018-03 | 1,152,656.99 | 980,977.65 | +17.5% | False |
| 2018-04 | 1,156,248.89 | 1,078,021.05 | +7.3% | False |
| 2018-05 | 1,145,686.46 | 1,096,130.68 | +4.5% | False |
| 2018-06 | 1,020,381.90 | 1,151,530.78 | -11.4% | False |
| 2018-07 | 1,039,783.58 | 1,107,439.08 | -6.1% | False |
| 2018-08 | 996,973.51 | 1,068,617.31 | -6.7% | False |

**Key finding:** With a 1.3× trailing-average threshold, Feb-May 2017 also flag as "spikes" — but that's **platform ramp-up/hyper-growth** (the trailing average is still tiny in the first few months), not calendar seasonality, and wouldn't recur once the marketplace matures. **Nov-2017 is the only spike during the post-ramp "mature" period** (Jun-2017 onward, where MoM growth has settled below ~25%) and lines up with **Black Friday** (Nov 24, 2017 in Brazil) — a genuine, recurring seasonality signal worth **+64% over trailing trend in a single month**. Operationally, this is the demand surge that Q3.7 shows degraded on-time delivery (14.31% late vs. ~5% baseline) — i.e., **Operations needs to scale carrier capacity ahead of the Nov-Dec peak**, the single highest-value, lowest-effort recommendation in this entire analysis. A second Black Friday data point (Nov-2018) would strengthen this further but is outside this extract's Sep-2018 cutoff.

---

## Domain 2: Customer RFM & Cohort Retention
*(`sql/analytics/02_customer_rfm_cohorts.sql`)* — the Amazon Retail customer-lifecycle lens.

**Headline structural finding (drives every query design choice below):** 93,099 of 96,096 customers (96.9%) place exactly **ONE** order ever; only 2,997 (3.1%) ever return. This is a well-documented characteristic of the Olist marketplace (sellers are mostly small/regional; customers often buy a one-off item and never return to that *specific seller's* catalog again — unlike a single-brand retailer where repeat purchase is the norm).

Why this matters for an Amazon-style read: classic RFM "Frequency" and cohort "retention curves" are designed for businesses where repeat purchase is common. Here, Frequency is degenerate (96.9% tie at F=1), so Q2.1 segments on **Recency × Monetary only**, with repeat-purchase status layered on as a separate flag. Cohort retention curves (Q2.3) will show ~2-3% month-1 retention across **every** cohort — not a broken query, but the central strategic finding: this marketplace currently looks **nothing like Amazon's repeat-purchase/Prime-driven model**, and GMV growth (Domain 1) is being driven almost entirely by **new-customer acquisition** (Q2.4), not retention. That is precisely the kind of gap an Amazon Retail BA would be expected to surface and act on (loyalty program, post-purchase email/coupon, subscribe-and-save analogues).

### Q2.1: RFM segmentation (Recency × Monetary quintiles)

**Business question:** Which customers are high-value-and-recent (nurture), high-value-but-lapsed (win-back priority), or low-value (low priority)?

```sql
WITH snapshot AS (
    SELECT (MAX(order_purchase_date) + INTERVAL '1 day')::date AS snapshot_date
    FROM marts.fact_orders
    WHERE order_status NOT IN ('canceled', 'unavailable')
),
customer_rfm AS (
    SELECT
        fo.customer_unique_id,
        (s.snapshot_date - MAX(fo.order_purchase_date))::int AS recency_days,
        COUNT(DISTINCT fo.order_id)                          AS frequency,
        SUM(fo.order_total_value)                            AS monetary
    FROM marts.fact_orders fo
    CROSS JOIN snapshot s
    WHERE fo.order_status NOT IN ('canceled', 'unavailable')
    GROUP BY fo.customer_unique_id, s.snapshot_date
),
scored AS (
    SELECT
        customer_unique_id, recency_days, frequency, monetary,
        NTILE(5) OVER (ORDER BY recency_days DESC) AS r_score,  -- 5 = most recent
        NTILE(5) OVER (ORDER BY monetary ASC)      AS m_score   -- 5 = highest spend
    FROM customer_rfm
)
SELECT
    r_score, m_score,
    CASE
        WHEN r_score >= 4 AND m_score >= 4 THEN 'Champions (recent + high spend)'
        WHEN r_score <= 2 AND m_score >= 4 THEN 'High-Value Lapsed (win-back priority)'
        WHEN r_score >= 4 AND m_score <= 2 THEN 'New/Recent Low-Spend'
        WHEN r_score <= 2 AND m_score <= 2 THEN 'Low-Value Lapsed'
        ELSE 'Mid-Value'
    END AS rfm_segment,
    COUNT(*)                                              AS n_customers,
    ROUND(100.0 * COUNT(*) / SUM(COUNT(*)) OVER (), 2)    AS pct_of_customers,
    SUM(CASE WHEN frequency > 1 THEN 1 ELSE 0 END)        AS n_repeat_customers,
    ROUND(AVG(monetary)::numeric, 2)                      AS avg_monetary,
    ROUND(AVG(recency_days)::numeric, 1)                  AS avg_recency_days,
    ROUND(SUM(monetary)::numeric, 2)                      AS segment_total_revenue
FROM scored
GROUP BY r_score, m_score, rfm_segment
ORDER BY r_score DESC, m_score DESC;
```

**Result** (25 rows = 5×5 R/M grid):

| r_score | m_score | rfm_segment | n_customers | % cust. | n_repeat | avg_monetary | avg_recency_days | segment_total_revenue |
|---|---|---|---|---|---|---|---|---|
| 5 | 5 | Champions (recent + high spend) | 3,867 | 4.07% | 378 | 450.36 | 52.9 | 1,741,532.02 |
| 5 | 4 | Champions (recent + high spend) | 3,917 | 4.12% | 148 | 165.90 | 51.9 | 649,815.48 |
| 5 | 3 | Mid-Value | 3,835 | 4.04% | 78 | 108.69 | 51.4 | 416,807.58 |
| 5 | 2 | New/Recent Low-Spend | 3,610 | 3.80% | 32 | 70.52 | 49.2 | 254,576.86 |
| 5 | 1 | New/Recent Low-Spend | 3,769 | 3.97% | 7 | 39.51 | 50.7 | 148,906.16 |
| 4 | 5 | Champions (recent + high spend) | 3,856 | 4.06% | 328 | 453.78 | 141.6 | 1,749,757.13 |
| 4 | 4 | Champions (recent + high spend) | 3,976 | 4.19% | 152 | 166.22 | 142.1 | 660,877.29 |
| 4 | 3 | Mid-Value | 3,866 | 4.07% | 74 | 108.32 | 140.0 | 418,758.82 |
| 4 | 2 | New/Recent Low-Spend | 3,619 | 3.81% | 30 | 70.46 | 142.2 | 254,984.76 |
| 4 | 1 | New/Recent Low-Spend | 3,681 | 3.88% | 9 | 39.81 | 142.0 | 146,558.43 |
| 3 | 5 | Mid-Value | 3,672 | 3.87% | 355 | 414.77 | 226.4 | 1,523,031.30 |
| 3 | 4 | Mid-Value | 3,973 | 4.18% | 159 | 165.47 | 226.3 | 657,421.78 |
| 3 | 3 | Mid-Value | 3,774 | 3.97% | 84 | 108.40 | 227.4 | 409,117.24 |
| 3 | 2 | Mid-Value | 3,656 | 3.85% | 25 | 70.45 | 226.1 | 257,564.89 |
| 3 | 1 | Mid-Value | 3,923 | 4.13% | 2 | 39.55 | 224.7 | 155,144.20 |
| 2 | 5 | High-Value Lapsed (win-back priority) | 3,804 | 4.00% | 293 | 454.85 | 322.8 | 1,730,247.34 |
| 2 | 4 | High-Value Lapsed (win-back priority) | 3,670 | 3.86% | 145 | 165.48 | 321.9 | 607,323.88 |
| 2 | 3 | Mid-Value | 3,761 | 3.96% | 94 | 108.67 | 322.7 | 408,698.57 |
| 2 | 2 | Low-Value Lapsed | 4,093 | 4.31% | 36 | 70.49 | 323.4 | 288,510.92 |
| 2 | 1 | Low-Value Lapsed | 3,670 | 3.86% | 3 | 40.02 | 321.6 | 146,873.82 |
| 1 | 5 | High-Value Lapsed (win-back priority) | 3,799 | 4.00% | 224 | 443.93 | 483.1 | 1,686,497.63 |
| 1 | 4 | High-Value Lapsed (win-back priority) | 3,462 | 3.64% | 114 | 164.33 | 478.7 | 568,898.03 |
| 1 | 3 | Mid-Value | 3,762 | 3.96% | 70 | 109.27 | 478.7 | 411,090.50 |
| 1 | 2 | Low-Value Lapsed | 4,020 | 4.23% | 40 | 71.05 | 477.8 | 285,618.41 |
| 1 | 1 | Low-Value Lapsed | 3,955 | 4.16% | 8 | 39.67 | 482.8 | 156,913.99 |

**Key finding:** Rolling these 25 cells up into the 5 named segments reproduces `dashboard/extracts/rfm_segment_summary.csv`: **Champions** (n=15,288, 16.5% of customers) drive **30.6% of revenue** — the highest revenue-per-customer-share ratio of any segment. **High-Value Lapsed** customers (n=14,446, 15.6% of customers, 29.3% of revenue, avg recency **398 days**) represent the single largest **win-back opportunity** in the dataset: these customers historically spent as much as Champions (avg_monetary R$310 vs R$306) but haven't ordered in over a year. Even a modest reactivation campaign targeting this segment — e.g. a "we miss you" discount — could be benchmarked against the R$4.48M this segment has already proven it's willing to spend. Note the **repeat-rate gradient within R=5** (highest m_score cell has 378/3867=9.8% repeat vs the lowest m_score cell's 7/3769=0.2%) — high spenders are disproportionately more likely to be repeat buyers, suggesting repeat purchase and spend reinforce each other.

---

### Q2.2: Repeat-purchase rate and time-to-second-order

**Business question:** How rare is repeat purchase, and for those who do return, how long does it take?

```sql
WITH order_seq AS (
    SELECT
        customer_unique_id,
        order_purchase_date,
        ROW_NUMBER() OVER (PARTITION BY customer_unique_id ORDER BY order_purchase_date, order_id) AS order_seq
    FROM marts.fact_orders
    WHERE order_status NOT IN ('canceled', 'unavailable')
),
first_two AS (
    SELECT
        customer_unique_id,
        MAX(CASE WHEN order_seq = 1 THEN order_purchase_date END) AS first_order_date,
        MAX(CASE WHEN order_seq = 2 THEN order_purchase_date END) AS second_order_date
    FROM order_seq
    WHERE order_seq <= 2
    GROUP BY customer_unique_id
    HAVING COUNT(*) = 2
)
SELECT
    (SELECT COUNT(*) FROM marts.dim_customer)                                   AS total_customers,
    (SELECT COUNT(*) FROM first_two)                                            AS repeat_customers,
    ROUND(100.0 * (SELECT COUNT(*) FROM first_two)
          / (SELECT COUNT(*) FROM marts.dim_customer), 2)                       AS repeat_rate_pct,
    ROUND(AVG(second_order_date - first_order_date), 1)                         AS avg_days_to_2nd_order,
    PERCENTILE_CONT(0.5) WITHIN GROUP (ORDER BY (second_order_date - first_order_date)) AS median_days_to_2nd_order,
    MIN(second_order_date - first_order_date)                                   AS min_days_to_2nd_order,
    MAX(second_order_date - first_order_date)                                   AS max_days_to_2nd_order
FROM first_two;
```

**Result** (1 row):

| total_customers | repeat_customers | repeat_rate_pct | avg_days_to_2nd_order | median_days_to_2nd_order | min_days_to_2nd_order | max_days_to_2nd_order |
|---|---|---|---|---|---|---|
| 96,096 | 2,888 | **3.01%** | 80.8 | 28.0 | 0 | 609 |

**Key finding:** Only **3.01%** of all customers (2,888 of 96,096) ever place a second order. (This is the "≥2 valid orders" cut — slightly tighter than Q2.1's 2,997, which counted any customer whose `frequency > 1` regardless of whether their orders fell in valid sequence pairs; the two numbers are consistent at the ~3% headline.) Of those who *do* return, the **median time to second order is 28 days** — but the **mean (80.8 days)** is pulled far higher by a long tail (max 609 days, i.e. some customers return after nearly two years). The **0-day minimum** likely reflects same-day multi-order customers (e.g. ordering from two different sellers on the same day) rather than true "loyalty." For an Amazon-style lifecycle program: the 28-day median is the natural window for a "come back" email/coupon — most repeat purchases that happen, happen within about a month, so retention marketing should be front-loaded into that window rather than spread evenly over a year.

---

### Q2.3: Acquisition-cohort retention curve, months 0-6

**Business question:** Of customers acquired in month X, what % place ANOTHER order in each of the following 6 months?

```sql
WITH customer_cohort AS (
    SELECT
        customer_unique_id,
        DATE_TRUNC('month', MIN(order_purchase_date))::date AS cohort_month
    FROM marts.fact_orders
    WHERE order_status NOT IN ('canceled', 'unavailable')
    GROUP BY 1
),
order_months AS (
    SELECT DISTINCT
        fo.customer_unique_id,
        DATE_TRUNC('month', fo.order_purchase_date)::date AS order_month
    FROM marts.fact_orders fo
    WHERE fo.order_status NOT IN ('canceled', 'unavailable')
),
activity AS (
    SELECT
        cc.cohort_month,
        cc.customer_unique_id,
        (EXTRACT(YEAR FROM om.order_month) - EXTRACT(YEAR FROM cc.cohort_month)) * 12
            + (EXTRACT(MONTH FROM om.order_month) - EXTRACT(MONTH FROM cc.cohort_month)) AS months_since_acquisition
    FROM customer_cohort cc
    JOIN order_months om ON om.customer_unique_id = cc.customer_unique_id
),
cohort_size AS (
    SELECT cohort_month, COUNT(*) AS cohort_customers
    FROM customer_cohort
    GROUP BY 1
)
SELECT
    a.cohort_month, cs.cohort_customers,
    a.months_since_acquisition::int AS months_since_acquisition,
    COUNT(DISTINCT a.customer_unique_id) AS active_customers,
    ROUND(100.0 * COUNT(DISTINCT a.customer_unique_id) / cs.cohort_customers, 2) AS retention_pct
FROM activity a
JOIN cohort_size cs ON cs.cohort_month = a.cohort_month
WHERE a.months_since_acquisition BETWEEN 0 AND 6
  AND a.cohort_month BETWEEN '2017-01-01' AND '2018-02-01'  -- cohorts need >=6mo of follow-up data (extract ends 2018-10)
GROUP BY a.cohort_month, cs.cohort_customers, a.months_since_acquisition
ORDER BY a.cohort_month, a.months_since_acquisition;
```

**Note:** Cohort month is derived from each customer's first **non-canceled** order (not `dim_customer.first_order_date`, which includes canceled/unavailable orders), so month-0 retention is 100% by construction — the standard cohort-analysis convention. This excludes 1,106 customers (1.2% of the 96,096 in `dim_customer`) whose entire order history is canceled/unavailable and who therefore never "joined" a revenue-generating cohort.

**Result** (98 rows = 14 cohorts × 7 months; full retention matrix below, pivoted for readability):

| cohort_month | cohort_size | m0 | m1 | m2 | m3 | m4 | m5 | m6 |
|---|---|---|---|---|---|---|---|---|
| 2017-01 | 752 | 100.00 | 0.40 | 0.27 | 0.13 | 0.40 | 0.13 | 0.40 |
| 2017-02 | 1,690 | 100.00 | 0.24 | 0.30 | 0.12 | 0.41 | 0.12 | 0.24 |
| 2017-03 | 2,571 | 100.00 | 0.51 | 0.35 | 0.39 | 0.35 | 0.16 | 0.16 |
| 2017-04 | 2,325 | 100.00 | 0.60 | 0.22 | 0.17 | 0.30 | 0.26 | 0.34 |
| 2017-05 | 3,541 | 100.00 | 0.48 | 0.48 | 0.40 | 0.31 | 0.34 | 0.42 |
| 2017-06 | 3,102 | 100.00 | 0.45 | 0.35 | 0.39 | 0.26 | 0.39 | 0.35 |
| 2017-07 | 3,822 | 100.00 | 0.52 | 0.34 | 0.24 | 0.29 | 0.21 | 0.31 |
| 2017-08 | 4,130 | 100.00 | 0.68 | 0.34 | 0.27 | 0.36 | 0.53 | 0.29 |
| 2017-09 | 4,075 | 100.00 | 0.69 | 0.54 | 0.29 | 0.44 | 0.22 | 0.22 |
| 2017-10 | 4,392 | 100.00 | 0.71 | 0.25 | 0.09 | 0.23 | 0.20 | 0.20 |
| 2017-11 | 7,190 | 100.00 | 0.56 | 0.39 | 0.17 | 0.19 | 0.18 | 0.11 |
| 2017-12 | 5,439 | 100.00 | 0.22 | 0.28 | 0.35 | 0.26 | 0.20 | 0.17 |
| 2018-01 | 6,951 | 100.00 | 0.33 | 0.36 | 0.29 | 0.29 | 0.16 | 0.17 |
| 2018-02 | 6,357 | 100.00 | 0.36 | 0.39 | 0.30 | 0.27 | 0.22 | 0.20 |
| **avg across all 14 cohorts** | | **100.00** | **0.48** | **0.35** | **0.26** | **0.31** | **0.24** | **0.26** |

**Key finding:** This is the starkest finding in the entire project. **Month-1 retention averages 0.48%** — i.e., of every ~1,000 newly acquired customers, fewer than 5 place another order the following month, and the curve **never recovers** (months 2-6 hover at 0.24-0.35%, essentially flat — there's no "decay curve" shape because there's almost nothing to decay from). Compare this to a typical e-commerce benchmark of 20-40% month-1 retention for a healthy repeat-purchase business. **Cohort size itself is growing** (752 → 7,190 from Jan-2017 to Nov-2017, tracking the GMV growth in Domain 1), but retention quality is **not improving over time** — the Nov-2017 cohort (the largest, acquired during the Black Friday surge) actually has *below-average* month-1 retention (0.56% vs the slight Aug/Sep/Oct-2017 cohorts' 0.68-0.71%), hinting that Black-Friday-acquired customers may be more price-driven/one-off than organically-acquired ones. **Bottom line for an Amazon BA:** any growth strategy here must be evaluated primarily on **new-customer acquisition efficiency** (CAC, channel mix), because the retention/LTV flywheel that justifies high CAC at Amazon (Prime, repeat Subscribe & Save, etc.) **does not currently exist on this platform** — building it (or a marketplace-appropriate analogue, like a seller-loyalty or platform-wide loyalty program) is the highest-leverage strategic recommendation Domain 2 surfaces.

---

### Q2.4: New vs. returning-customer share of orders & GMV

**Business question:** How much of our growth (Domain 1) is new-customer acquisition vs. existing-customer reactivation?

```sql
WITH order_seq AS (
    SELECT
        order_id, customer_unique_id, order_purchase_date, order_total_value,
        ROW_NUMBER() OVER (PARTITION BY customer_unique_id ORDER BY order_purchase_date, order_id) AS order_seq
    FROM marts.fact_orders
    WHERE order_status NOT IN ('canceled', 'unavailable')
)
SELECT
    DATE_TRUNC('month', order_purchase_date)::date AS month,
    COUNT(*)                                                            AS n_orders,
    SUM(CASE WHEN order_seq = 1 THEN 1 ELSE 0 END)                      AS new_customer_orders,
    SUM(CASE WHEN order_seq > 1 THEN 1 ELSE 0 END)                      AS returning_customer_orders,
    ROUND(100.0 * SUM(CASE WHEN order_seq > 1 THEN 1 ELSE 0 END) / COUNT(*), 2) AS pct_orders_from_returning,
    ROUND(SUM(order_total_value)::numeric, 2)                           AS gmv,
    ROUND(SUM(CASE WHEN order_seq > 1 THEN order_total_value ELSE 0 END)::numeric, 2) AS returning_customer_gmv,
    ROUND(100.0 * SUM(CASE WHEN order_seq > 1 THEN order_total_value ELSE 0 END)
          / SUM(order_total_value), 2)                                  AS pct_gmv_from_returning
FROM order_seq
WHERE order_purchase_date BETWEEN '2017-01-01' AND '2018-08-31'
GROUP BY 1
ORDER BY 1;
```

**Note:** `order_seq` is computed over each customer's **full order history** (not just the reporting window), so a 2018 order from a 2016/2017-acquired customer is correctly counted as "returning."

**Result** (20 rows):

| month | n_orders | new_orders | returning_orders | % returning orders | gmv | returning_gmv | % returning GMV |
|---|---|---|---|---|---|---|---|
| 2017-01 | 787 | 752 | 35 | 4.45% | 136,943.46 | 2,689.96 | 1.96% |
| 2017-02 | 1,718 | 1,690 | 28 | 1.63% | 283,561.69 | 3,476.56 | 1.23% |
| 2017-03 | 2,617 | 2,571 | 46 | 1.76% | 425,617.96 | 4,939.52 | 1.16% |
| 2017-04 | 2,377 | 2,325 | 52 | 2.19% | 405,848.61 | 10,241.96 | 2.52% |
| 2017-05 | 3,640 | 3,541 | 99 | 2.72% | 582,710.83 | 15,441.69 | 2.65% |
| 2017-06 | 3,205 | 3,102 | 103 | 3.21% | 499,652.24 | 12,040.27 | 2.41% |
| 2017-07 | 3,946 | 3,822 | 124 | 3.14% | 578,753.73 | 18,299.98 | 3.16% |
| 2017-08 | 4,272 | 4,130 | 142 | 3.32% | 661,903.52 | 21,649.49 | 3.27% |
| 2017-09 | 4,227 | 4,075 | 152 | 3.60% | 717,102.72 | 23,179.58 | 3.23% |
| 2017-10 | 4,547 | 4,392 | 155 | 3.41% | 764,756.03 | 19,992.85 | 2.61% |
| 2017-11 | 7,423 | 7,190 | 233 | 3.14% | 1,172,191.68 | 30,638.44 | 2.61% |
| 2017-12 | 5,620 | 5,439 | 181 | 3.22% | 861,526.77 | 29,234.21 | 3.39% |
| 2018-01 | 7,187 | 6,951 | 236 | 3.28% | 1,101,920.01 | 35,136.60 | 3.19% |
| 2018-02 | 6,625 | 6,357 | 268 | **4.05%** | 979,486.16 | 35,280.05 | 3.60% |
| 2018-03 | 7,168 | 6,931 | 237 | 3.31% | 1,152,656.99 | 33,637.60 | 2.92% |
| 2018-04 | 6,919 | 6,698 | 221 | 3.19% | 1,156,248.89 | 33,669.92 | 2.91% |
| 2018-05 | 6,833 | 6,586 | 247 | 3.61% | 1,145,686.46 | 38,819.27 | 3.39% |
| 2018-06 | 6,145 | 5,920 | 225 | 3.66% | 1,020,381.90 | 34,644.08 | 3.40% |
| 2018-07 | 6,233 | 6,016 | 217 | 3.48% | 1,039,783.58 | 32,330.80 | 3.11% |
| 2018-08 | 6,421 | 6,209 | 212 | 3.30% | 996,973.51 | 32,020.48 | 3.21% |

**Key finding:** Returning customers consistently contribute **3-4% of orders and roughly the same share of GMV** — meaning returning customers spend at roughly the **same AOV** as new customers (no meaningful "loyal customers spend more" effect is visible at the order-level monthly view, though Q2.1 shows it does exist within the high-monetary RFM cells). The returning share has been **essentially flat for the entire 20-month window** (1.6% in early 2017 rising only to ~3.3% by mid-2018, after an initial ramp from the near-zero values typical of a brand-new platform) — confirming Q2.3's finding quantitatively: **96.5-98% of every month's GMV comes from customers buying for the first time ever**. For Domain 1's "what's the next growth lever" question, this query provides the answer in dollar terms: **of the R$15.68M total GMV (Q1.2), only ~R$450K (~2.9%) came from returning customers** — the other ~97% is acquisition-driven, and acquisition-driven growth has a ceiling (eventually you run out of new Brazilian internet shoppers to acquire, or CAC rises). This is the quantified business case for retention investment.

---

### Q2.5: Customer LTV distribution and revenue concentration by decile

**Business question:** How much of total revenue depends on a small group of high-spend customers?

```sql
WITH customer_value AS (
    SELECT
        customer_unique_id,
        SUM(order_total_value) AS total_spend,
        COUNT(*)               AS n_orders
    FROM marts.fact_orders
    WHERE order_status NOT IN ('canceled', 'unavailable')
    GROUP BY 1
),
deciles AS (
    SELECT
        customer_unique_id, total_spend,
        NTILE(10) OVER (ORDER BY total_spend DESC) AS spend_decile
    FROM customer_value
)
SELECT
    spend_decile,
    COUNT(*)                                                                 AS n_customers,
    ROUND(MIN(total_spend)::numeric, 2)                                      AS min_spend_in_decile,
    ROUND(MAX(total_spend)::numeric, 2)                                      AS max_spend_in_decile,
    ROUND(SUM(total_spend)::numeric, 2)                                      AS decile_revenue,
    ROUND(100.0 * SUM(total_spend) / SUM(SUM(total_spend)) OVER (), 2)       AS pct_of_total_revenue,
    ROUND(100.0 * SUM(SUM(total_spend)) OVER (ORDER BY spend_decile)
          / SUM(SUM(total_spend)) OVER (), 2)                                AS cumulative_pct_of_revenue
FROM deciles
GROUP BY spend_decile
ORDER BY spend_decile;
```

**Result** (10 rows, n=94,990 customers with ≥1 valid order):

| spend_decile | n_customers | min_spend | max_spend | decile_revenue | % of total | cumulative % |
|---|---|---|---|---|---|---|
| 1 (highest) | 9,499 | 318.97 | 13,664.08 | 6,025,467.51 | **38.29%** | 38.29% |
| 2 | 9,499 | 209.11 | 318.97 | 2,405,597.91 | 15.29% | 53.58% |
| 3 | 9,499 | 163.25 | 209.11 | 1,746,064.23 | 11.10% | 64.68% |
| 4 | 9,499 | 133.05 | 163.25 | 1,398,272.23 | 8.89% | 73.56% |
| 5 | 9,499 | 107.90 | 133.04 | 1,137,729.22 | 7.23% | 80.79% |
| 6 | 9,499 | 87.50 | 107.90 | 926,743.49 | 5.89% | 86.68% |
| 7 | 9,499 | 70.00 | 87.48 | 744,367.96 | 4.73% | 91.41% |
| 8 | 9,499 | 55.34 | 69.99 | 596,887.88 | 3.79% | 95.21% |
| 9 | 9,499 | 40.10 | 55.33 | 453,748.79 | 2.88% | 98.09% |
| 10 (lowest) | 9,499 | 0.00 | 40.10 | 300,647.81 | 1.91% | 100.00% |

**Key finding:** The **top 10% of customers generate 38.3% of total revenue**, and the **top 30%** generate **64.7%** — a meaningfully concentrated distribution, though less extreme than the seller-side Pareto (Q4.1: top 10% of sellers = 67.6% of revenue). Decile 1's spend range (R$318.97 - R$13,664.08) is wide, meaning even within the "top 10%" there's a further long tail of a handful of exceptionally high-value customers — likely small businesses or bulk buyers rather than typical consumers (worth a follow-up query to check order count / category mix for the top ~50 individual customers). Decile 10's **minimum spend of R$0.00** likely reflects the small number of orders where `order_total_value` rounds to zero (e.g. free promotional items) — a minor data-quality curiosity rather than a meaningful segment. The strategic read: a **10% revenue decline among the top decile would be roughly equivalent to losing the bottom 5 deciles entirely** — i.e., this customer base, while not as extreme as the seller base, still warrants a "VIP" retention/account-management lens disproportionate to its headcount.

---

### Q2.6: Customer geography — order volume, GMV, AOV by state

**Business question:** Which states drive the marketplace, and where is AOV meaningfully higher/lower than the national average (pricing/logistics implications)?

```sql
WITH state_agg AS (
    SELECT
        customer_state,
        COUNT(DISTINCT customer_unique_id) AS n_customers,
        COUNT(*)                           AS n_orders,
        SUM(order_total_value)             AS gmv
    FROM marts.fact_orders
    WHERE order_status NOT IN ('canceled', 'unavailable')
    GROUP BY 1
)
SELECT
    customer_state, n_customers, n_orders,
    ROUND(gmv::numeric, 2)                                                AS gmv,
    ROUND((gmv / n_orders)::numeric, 2)                                   AS aov,
    ROUND(100.0 * gmv / SUM(gmv) OVER (), 2)                              AS pct_of_total_gmv,
    ROUND(100.0 * SUM(gmv) OVER (ORDER BY gmv DESC) / SUM(gmv) OVER (), 2) AS cumulative_pct_gmv,
    RANK() OVER (ORDER BY gmv DESC)                                       AS gmv_rank
FROM state_agg
ORDER BY gmv DESC;
```

**Result** (27 rows = all Brazilian states + DF):

| rank | state | n_customers | n_orders | gmv | aov | % of GMV | cumulative % |
|---|---|---|---|---|---|---|---|
| 1 | SP | 39,749 | 41,127 | 5,878,132.06 | 142.93 | 37.36% | 37.36% |
| 2 | RJ | 12,242 | 12,698 | 2,115,667.56 | 166.61 | 13.45% | 50.80% |
| 3 | MG | 11,134 | 11,496 | 1,843,074.43 | 160.32 | 11.71% | 62.51% |
| 4 | RS | 5,234 | 5,417 | 877,290.59 | 161.95 | 5.58% | 68.09% |
| 5 | PR | 4,825 | 4,983 | 794,196.61 | 159.38 | 5.05% | 73.14% |
| 6 | SC | 3,502 | 3,600 | 608,023.70 | 168.90 | 3.86% | 77.00% |
| 7 | BA | 3,244 | 3,344 | 606,908.66 | 181.49 | 3.86% | 80.86% |
| 8 | DF | 2,058 | 2,121 | 351,327.21 | 165.64 | 2.23% | 83.09% |
| 9 | GO | 1,934 | 1,998 | 340,544.37 | 170.44 | 2.16% | 85.25% |
| 10 | ES | 1,950 | 2,018 | 323,081.03 | 160.10 | 2.05% | 87.31% |
| 11 | PE | 1,600 | 1,643 | 321,018.34 | 195.39 | 2.04% | 89.35% |
| 12 | CE | 1,301 | 1,323 | 274,522.61 | 207.50 | 1.74% | 91.09% |
| 13 | PA | 944 | 969 | 217,480.54 | 224.44 | 1.38% | 92.47% |
| 14 | MT | 872 | 902 | 186,005.11 | 206.21 | 1.18% | 93.66% |
| 15 | MA | 715 | 736 | 150,687.96 | 204.74 | 0.96% | 94.61% |
| 16 | PB | 516 | 531 | 140,523.47 | 264.64 | 0.89% | 95.51% |
| 17 | MS | 687 | 708 | 135,875.69 | 191.91 | 0.86% | 96.37% |
| 18 | PI | 478 | 490 | 107,765.47 | 219.93 | 0.68% | 97.06% |
| 19 | RN | 471 | 482 | 101,895.08 | 211.40 | 0.65% | 97.70% |
| 20 | AL | 399 | 411 | 96,229.40 | 234.13 | 0.61% | 98.31% |
| 21 | SE | 338 | 345 | 73,032.32 | 211.69 | 0.46% | 98.78% |
| 22 | TO | 271 | 278 | 61,103.85 | 219.80 | 0.39% | 99.17% |
| 23 | RO | 234 | 246 | 57,423.77 | 233.43 | 0.36% | 99.53% |
| 24 | AM | 142 | 147 | 27,835.73 | 189.36 | 0.18% | 99.71% |
| 25 | AC | 77 | 81 | 19,669.70 | 242.84 | 0.13% | 99.83% |
| 26 | AP | 67 | 68 | 16,262.80 | 239.16 | 0.10% | 99.94% |
| 27 | RR | 44 | 45 | 9,948.97 | 221.09 | 0.06% | 100.00% |

**Key finding:** **SP + RJ + MG = 62.51%** of GMV — the demand side is heavily concentrated in Brazil's industrial/economic core (Southeast region). But the **AOV pattern inverts the GMV pattern**: SP has both the highest GMV share *and* the **lowest AOV (R$142.93)** — the national average, weighted by volume, sits around R$155-160. The **highest-AOV states are all small, remote, North/Northeast states** — PB (R$264.64), AC (R$242.84), AP (R$239.16), AL (R$234.13), PA (R$224.44) — states with the fewest customers but where each order is worth nearly **2x** SP's AOV. The likely explanation (consistent with Q4.4's freight findings): customers in remote states pay higher freight (bundled into `order_total_value`), and/or place fewer, larger/bulk orders to amortize that freight cost across more items. This is a direct pricing/logistics signal: **a flat national shipping promo would disproportionately benefit (and could disproportionately stimulate demand in) these high-AOV remote states** — exactly the kind of geographic expansion lever an Amazon Retail BA evaluating "where's our next regional growth market" would flag.

---

## Domain 3: Fulfillment & Operations
*(`sql/analytics/03_fulfillment_ops.sql`)* — the Amazon Operations/Fulfillment lens: order-to-delivery cycle time broken into stages (seller processing, carrier handoff, line-haul/transit), promise-date ("estimated delivery date") accuracy, on-time delivery rate (OTD) by geography and time, and the downstream impact of late delivery on customer satisfaction.

**DQ-flag handling note** (applies throughout this domain): per `docs/data_quality_report.md`, 1.37% of orders have `order_delivered_carrier_date < order_approved_at` (`dq_carrier_before_approval`) and 0.02% have `order_delivered_customer_date < order_delivered_carrier_date` (`dq_delivered_before_carrier`) — source-data timestamp anomalies. Every stage-timing query below excludes the affected rows from **that stage's** average only (the row's revenue/review data is still valid and used elsewhere).

### Q3.1: Order status funnel

**Business question:** What % of demand converts to a completed delivery, and how much is lost to cancellation/unavailability?

```sql
SELECT
    order_status,
    COUNT(*) AS n_orders,
    ROUND(100.0 * COUNT(*) / SUM(COUNT(*)) OVER (), 2) AS pct_of_orders
FROM marts.fact_orders
GROUP BY 1
ORDER BY n_orders DESC;
```

**Result** (8 rows, all 99,441 orders):

| order_status | n_orders | pct_of_orders |
|---|---|---|
| delivered | 96,478 | 97.02% |
| shipped | 1,107 | 1.11% |
| canceled | 625 | 0.63% |
| unavailable | 609 | 0.61% |
| invoiced | 314 | 0.32% |
| processing | 301 | 0.30% |
| created | 5 | 0.01% |
| approved | 2 | 0.00% |

**Key finding:** **97.02%** of all orders ever placed reach `delivered` status — an excellent fulfillment funnel by e-commerce standards. Only **0.63% are canceled** and **0.61% unavailable** (the two statuses excluded from "valid orders" throughout this catalog). The remaining **2.34%** are "in flight" at the data extract's cutoff (shipped/invoiced/processing/created/approved) — these are not failures, just orders that hadn't completed by the Sep-2018 extract date. **For Operations, the headline is reassuring**: demand loss to cancellation is low (under 1.3% combined for canceled+unavailable), so the fulfillment problems quantified later in this domain (late deliveries) are a **service-quality** issue on top of an already-successful conversion funnel, not a conversion/availability problem.

---

### Q3.2: Monthly on-time delivery rate (OTD) & cycle time

**Business question:** Is delivery performance improving, holding steady, or degrading as order volume grows?

```sql
WITH monthly AS (
    SELECT
        DATE_TRUNC('month', order_purchase_date)::date AS month,
        COUNT(*)                                        AS n_delivered,
        SUM(CASE WHEN is_late THEN 1 ELSE 0 END)        AS n_late,
        AVG(actual_delivery_days)                       AS avg_actual_days,
        AVG(delivery_delay_days)                        AS avg_delay_days
    FROM marts.fact_orders
    WHERE is_delivered AND NOT dq_delivered_missing_date
      AND order_purchase_date BETWEEN '2017-01-01' AND '2018-08-31'
    GROUP BY 1
)
SELECT
    month, n_delivered, n_late,
    ROUND(100.0 * n_late / n_delivered, 2) AS pct_late,
    ROUND(avg_actual_days::numeric, 2)     AS avg_actual_delivery_days,
    ROUND(avg_delay_days::numeric, 2)      AS avg_delay_days,
    ROUND((100.0 * n_late / n_delivered
           - LAG(100.0 * n_late / n_delivered) OVER (ORDER BY month))::numeric, 2) AS pct_late_pp_mom_change
FROM monthly
ORDER BY month;
```

**Result** (20 rows; the Feb-Mar 2018 spike that Q3.8 drills into is in **bold**):

| month | n_delivered | n_late | pct_late | avg_actual_days | avg_delay_days | pp MoM change |
|---|---|---|---|---|---|---|
| 2017-01 | 750 | 23 | 3.07% | 12.65 | -26.86 | — |
| 2017-02 | 1,653 | 53 | 3.21% | 13.17 | -18.68 | +0.14 |
| 2017-03 | 2,546 | 142 | 5.58% | 12.95 | -11.78 | +2.37 |
| 2017-04 | 2,303 | 181 | 7.86% | 14.92 | -12.43 | +2.28 |
| 2017-05 | 3,545 | 128 | 3.61% | 11.32 | -12.96 | -4.25 |
| 2017-06 | 3,135 | 121 | 3.86% | 12.01 | -12.01 | +0.25 |
| 2017-07 | 3,872 | 133 | 3.43% | 11.59 | -11.72 | -0.42 |
| 2017-08 | 4,193 | 139 | 3.32% | 11.15 | -12.33 | -0.12 |
| 2017-09 | 4,150 | 216 | 5.20% | 11.85 | -10.59 | +1.89 |
| 2017-10 | 4,478 | 237 | 5.29% | 11.86 | -11.16 | +0.09 |
| 2017-11 | 7,288 | 1,043 | 14.31% | 15.16 | -7.40 | +9.02 |
| 2017-12 | 5,513 | 462 | 8.38% | 15.39 | -12.29 | -5.93 |
| 2018-01 | 7,069 | 464 | 6.56% | 14.08 | -12.22 | -1.82 |
| **2018-02** | 6,555 | 1,048 | **15.99%** | 16.95 | -7.58 | **+9.42** |
| **2018-03** | 7,003 | 1,496 | **21.36%** | 16.30 | -5.73 | **+5.37** |
| 2018-04 | 6,798 | 361 | 5.31% | 11.50 | -12.18 | -16.05 |
| 2018-05 | 6,749 | 556 | 8.24% | 11.42 | -11.47 | +2.93 |
| 2018-06 | 6,096 | 83 | 1.36% | 9.24 | -18.53 | -6.88 |
| 2018-07 | 6,156 | 276 | 4.48% | 8.96 | -10.73 | +3.12 |
| 2018-08 | 6,351 | 660 | 10.39% | 7.73 | -7.45 | +5.91 |

**Key finding:** Two distinct anomalies stand out against a baseline late-rate of roughly **3-8%**: the **Nov-2017 Black Friday spike** (14.31% late, the Q1.7 seasonal demand surge straining capacity — confirmed and quantified in Q3.7), and a **much larger, unexplained spike in Feb-Mar 2018** (15.99% → 21.36% late, more than **2x** the Black Friday effect) — this is the single biggest fulfillment anomaly in the dataset and is drilled into in Q3.8. Encouragingly, **`avg_delay_days` is negative throughout** (orders arrive *before* the estimate on average, by 6-27 days) even in the worst months — meaning Olist's promised delivery windows are **conservatively padded** (confirmed in Q3.6), which cushions the customer-experience impact of these spikes but also raises a separate question about whether over-promising-slow estimates hurt conversion. **2018 H2 shows no sustained improvement** — Aug-2018 (10.39% late) is worse than most of H1, suggesting the Feb-Mar issue, while it recovered, did not trigger a lasting capacity fix, and similar Aug-2018 degradation could recur.

---

### Q3.3: Fulfillment cycle-time stage breakdown

**Business question:** Where does time go between purchase and delivery — seller processing (approval→carrier), carrier pickup-to-delivery (transit), or overall? Which stage has the heaviest right tail (p90)?

```sql
SELECT 'approval_hours (purchase -> approved)' AS stage,
       COUNT(*)                                            AS n,
       ROUND(AVG(approval_hours)::numeric, 2)              AS avg_value,
       ROUND(PERCENTILE_CONT(0.5) WITHIN GROUP (ORDER BY approval_hours)::numeric, 2) AS median_value,
       ROUND(PERCENTILE_CONT(0.9) WITHIN GROUP (ORDER BY approval_hours)::numeric, 2) AS p90_value,
       'hours' AS unit
FROM marts.fact_orders
WHERE order_approved_at IS NOT NULL

UNION ALL
SELECT 'carrier_handoff_days (approved -> carrier)',
       COUNT(*),
       ROUND(AVG(carrier_handoff_days)::numeric, 2),
       ROUND(PERCENTILE_CONT(0.5) WITHIN GROUP (ORDER BY carrier_handoff_days)::numeric, 2),
       ROUND(PERCENTILE_CONT(0.9) WITHIN GROUP (ORDER BY carrier_handoff_days)::numeric, 2),
       'days'
FROM marts.fact_orders
WHERE order_delivered_carrier_date IS NOT NULL AND NOT dq_carrier_before_approval

UNION ALL
SELECT 'shipping_transit_days (carrier -> customer)',
       COUNT(*),
       ROUND(AVG(shipping_transit_days)::numeric, 2),
       ROUND(PERCENTILE_CONT(0.5) WITHIN GROUP (ORDER BY shipping_transit_days)::numeric, 2),
       ROUND(PERCENTILE_CONT(0.9) WITHIN GROUP (ORDER BY shipping_transit_days)::numeric, 2),
       'days'
FROM marts.fact_orders
WHERE order_delivered_customer_date IS NOT NULL AND order_delivered_carrier_date IS NOT NULL
  AND NOT dq_delivered_before_carrier

UNION ALL
SELECT 'actual_delivery_days (purchase -> customer, end-to-end)',
       COUNT(*),
       ROUND(AVG(actual_delivery_days)::numeric, 2),
       ROUND(PERCENTILE_CONT(0.5) WITHIN GROUP (ORDER BY actual_delivery_days)::numeric, 2),
       ROUND(PERCENTILE_CONT(0.9) WITHIN GROUP (ORDER BY actual_delivery_days)::numeric, 2),
       'days'
FROM marts.fact_orders
WHERE is_delivered AND NOT dq_delivered_missing_date;
```

**Result** (4 rows):

| stage | n | avg | median | p90 | unit |
|---|---|---|---|---|---|
| approval_hours (purchase → approved) | 99,281 | 10.42 | 0.34 | 34.66 | hours |
| carrier_handoff_days (approved → carrier) | 96,299 | 2.86 | 1.85 | 6.03 | days |
| shipping_transit_days (carrier → customer) | 96,452 | 9.33 | 7.10 | 18.90 | days |
| actual_delivery_days (purchase → customer, end-to-end) | 96,470 | 12.56 | 10.22 | 23.10 | days |

**Key finding:** **Shipping transit (carrier → customer) is by far the dominant and most variable stage** — averaging **9.33 days** (median 7.10, p90 18.90) out of a total end-to-end average of **12.56 days**. That means transit alone accounts for ~74% of total delivery time on average. The **approval stage has the most extreme median-vs-mean gap**: median 0.34 hours (~20 minutes — essentially instant, automated payment approval) but a mean of 10.42 hours and a **p90 of 34.66 hours** — i.e., a small fraction of orders take >1.5 days just to get payment-approved, likely manual review or payment-method-related (boleto bank-slip payments in Brazil can take 1-3 business days to clear). **Carrier handoff (seller packing & dispatch) is comparatively well-controlled**: median 1.85 days, p90 6.03 days — sellers are not the primary bottleneck. **For an Operations BA, the prioritization is clear**: the highest-impact lever is **transit time** (line-haul/last-mile logistics, likely tied to the cross-state freight patterns in Q4.4), not seller behavior. The approval-stage p90 tail (34.66 hours) is a secondary, lower-volume issue worth a follow-up segmentation by payment type.

---

### Q3.4: On-time delivery rate by customer state

**Business question:** Which delivery regions need carrier/logistics intervention, and how does delivery time scale with distance from the SP/RJ/MG core (Domain 2, Q2.6)?

```sql
WITH state_perf AS (
    SELECT
        customer_state,
        COUNT(*)                                  AS n_delivered,
        SUM(CASE WHEN is_late THEN 1 ELSE 0 END)  AS n_late,
        AVG(actual_delivery_days)                 AS avg_actual_days,
        AVG(delivery_delay_days)                  AS avg_delay_days
    FROM marts.fact_orders
    WHERE is_delivered AND NOT dq_delivered_missing_date
    GROUP BY 1
    HAVING COUNT(*) >= 30
)
SELECT
    customer_state, n_delivered, n_late,
    ROUND(100.0 * n_late / n_delivered, 2)   AS pct_late,
    ROUND(avg_actual_days::numeric, 2)       AS avg_actual_delivery_days,
    ROUND(avg_delay_days::numeric, 2)        AS avg_delay_days,
    RANK() OVER (ORDER BY 100.0 * n_late / n_delivered DESC) AS worst_otd_rank
FROM state_perf
ORDER BY pct_late DESC;
```

**Result** (27 rows = all states with ≥30 delivered orders; worst 10 and best 5 shown — full 27-row table in `dashboard/extracts/geo_customer_state_summary.csv`):

**Worst on-time delivery (highest late %):**

| rank | state | n_delivered | n_late | pct_late | avg_actual_days | avg_delay_days |
|---|---|---|---|---|---|---|
| 1 | AL | 397 | 95 | **23.93%** | 24.54 | -8.03 |
| 2 | MA | 717 | 141 | 19.67% | 21.57 | -8.89 |
| 3 | PI | 476 | 76 | 15.97% | 19.46 | -10.63 |
| 4 | CE | 1,279 | 196 | 15.32% | 21.27 | -10.11 |
| 5 | SE | 335 | 51 | 15.22% | 21.52 | -9.33 |
| 6 | BA | 3,256 | 457 | 14.04% | 19.34 | -10.10 |
| 7 | RJ | 12,350 | 1,664 | 13.47% | 15.31 | -11.05 |
| 8 | TO | 274 | 35 | 12.77% | 17.66 | -11.44 |
| 9 | PA | 946 | 117 | 12.37% | 23.77 | -13.39 |
| 10 | ES | 1,995 | 244 | 12.23% | 15.79 | -9.80 |

**Best on-time delivery (lowest late %):**

| rank | state | n_delivered | n_late | pct_late | avg_actual_days | avg_delay_days |
|---|---|---|---|---|---|---|
| 23 | AP | 67 | 3 | 4.48% | 27.19 | -19.06 |
| 24 | AM | 145 | 6 | 4.14% | 26.43 | -18.85 |
| 25 | AC | 80 | 3 | 3.75% | 21.04 | -20.08 |
| 26 | RO | 243 | 7 | 2.88% | 19.37 | -19.40 |
| (21) | SP | 40,494 | 2,387 | 5.89% | 8.76 | -10.38 |

**Key finding:** This is a genuinely counter-intuitive finding worth featuring prominently: **the states with the LONGEST absolute delivery times (AM, AC, RO, AP — all 19-27 day average deliveries) have the LOWEST late rates (2.9-4.5%)**, while several states with shorter absolute delivery times (AL: 24.54 days avg but still 23.93% late; RJ: just 15.31 days avg but 13.47% late) are the **worst performers on the late-rate metric**. The explanation is in `avg_delay_days`: remote North-region states (AM, AC, RO, AP) have the **most conservative estimates** (avg_delay_days ≈ -19 to -20, i.e. Olist promises ~3 weeks but typically delivers faster) — so almost nothing is late *relative to a generously padded promise*, even though absolute delivery time is the longest in the country. Conversely, **AL, MA, RJ have tighter promise windows relative to actual performance**, so the same logistics network produces a much higher late rate. **The actionable insight**: the late-rate metric is a function of **promise-setting (Q3.6) as much as actual logistics performance** — fixing AL/MA/RJ's late rate could be as simple as **re-calibrating their estimated delivery dates** to match the more conservative North-region pattern, a low-cost "promise engineering" fix versus a costly logistics-network fix. **RJ is the highest-priority state** given it's also the #2 state by GMV (Q2.6) — 12,350 delivered orders at 13.47% late is the largest absolute volume of late deliveries of any state.

---

### Q3.5: Delivery-delay bucket vs. review score

**Business question:** How strongly does a late delivery hurt customer satisfaction, and at what delay threshold does the damage accelerate? *(Full statistical hypothesis test of this relationship is in the Python EDA phase — Notebook 4 — this is the descriptive SQL-level cut.)*

```sql
WITH bucketed AS (
    SELECT
        CASE
            WHEN delivery_delay_days <= -2                          THEN '1. Early (2+ days ahead)'
            WHEN delivery_delay_days > -2 AND delivery_delay_days <= 0 THEN '2. On-time (0-1 day ahead)'
            WHEN delivery_delay_days > 0  AND delivery_delay_days <= 3 THEN '3. Late 1-3 days'
            WHEN delivery_delay_days > 3  AND delivery_delay_days <= 7 THEN '4. Late 4-7 days'
            ELSE '5. Late 8+ days'
        END AS delay_bucket,
        review_score
    FROM marts.fact_orders
    WHERE is_delivered AND NOT dq_delivered_missing_date AND review_score IS NOT NULL
)
SELECT
    delay_bucket,
    COUNT(*)                                                              AS n_orders,
    ROUND(AVG(review_score)::numeric, 2)                                  AS avg_review_score,
    ROUND(100.0 * SUM(CASE WHEN review_score = 1 THEN 1 ELSE 0 END) / COUNT(*), 2) AS pct_1star,
    ROUND(100.0 * SUM(CASE WHEN review_score = 5 THEN 1 ELSE 0 END) / COUNT(*), 2) AS pct_5star
FROM bucketed
GROUP BY delay_bucket
ORDER BY delay_bucket;
```

**Result** (5 rows, n=95,824 delivered & reviewed orders — this is exactly the `risk_scores_negative_review.csv` population from `docs/data_dictionary.md` §Page 7):

| delay_bucket | n_orders | avg_review_score | pct_1star | pct_5star |
|---|---|---|---|---|
| 1. Early (2+ days ahead) | 85,173 | 4.30 | 6.55% | 62.67% |
| 2. On-time (0-1 day ahead) | 2,990 | 4.14 | 7.89% | 55.45% |
| 3. Late 1-3 days | 2,636 | 3.77 | 13.77% | 43.21% |
| 4. Late 4-7 days | 1,773 | 2.32 | 53.02% | 18.16% |
| 5. Late 8+ days | 3,252 | 1.73 | 68.82% | 7.47% |

**Key finding:** The relationship is **strongly non-linear with a sharp inflection point between "1-3 days late" and "4-7 days late"**: average review score barely moves from "Early" (4.30) to "1-3 days late" (3.77) — a drop of only 0.53 — but then **collapses by another 1.45 points to 2.32** for 4-7 days late, and the 1-star rate **nearly quadruples** (13.77% → 53.02%). By 8+ days late, **68.82% of orders get a 1-star review** and only 7.47% get 5-star — almost a complete reversal of the "Early" distribution (6.55% / 62.67%). **The business implication is precise**: a delivery that's a *little* late (1-3 days) is largely tolerated, but **crossing the ~4-day-late threshold triggers a qualitatively different, much angrier customer response** — this is the single most important number for any "should we intervene on this at-risk order" decision (and is exactly the post-delivery feature set, `is_late`/`delivery_delay_days`, that Model B in Notebook 6 uses as its top two predictors, importance 32.5% and 39.4% respectively). **Operationally**: a proactive-outreach program (apology + discount/refund-on-shipping) targeting orders that are tracking toward 4+ days late — *before* delivery completes — would target exactly the inflection point where review damage becomes severe, potentially saving the ~5,025 orders (1,773+3,252) currently landing in the two worst buckets from becoming 1-star reviews.

---

### Q3.6: Estimated-delivery-date accuracy distribution

**Business question:** How well-calibrated is Olist's delivery promise? Is the platform over-promising (frequent lateness) or under-promising (padding estimates, which hurts conversion even when delivery is "on time")?

```sql
WITH bucketed AS (
    SELECT
        CASE
            WHEN delivery_delay_days <= -15 THEN '1. 15+ days ahead of estimate'
            WHEN delivery_delay_days <= -7  THEN '2. 7-14 days ahead of estimate'
            WHEN delivery_delay_days <  0   THEN '3. 1-6 days ahead of estimate'
            WHEN delivery_delay_days =  0   THEN '4. On the estimated day'
            WHEN delivery_delay_days <= 7   THEN '5. 1-7 days late'
            ELSE '6. 8+ days late'
        END AS delivery_vs_estimate
    FROM marts.fact_orders
    WHERE is_delivered AND NOT dq_delivered_missing_date
)
SELECT
    delivery_vs_estimate,
    COUNT(*)                                                                AS n_orders,
    ROUND(100.0 * COUNT(*) / SUM(COUNT(*)) OVER (), 2)                      AS pct_of_delivered,
    ROUND(100.0 * SUM(COUNT(*)) OVER (ORDER BY delivery_vs_estimate)
          / SUM(COUNT(*)) OVER (), 2)                                       AS cumulative_pct
FROM bucketed
GROUP BY delivery_vs_estimate
ORDER BY delivery_vs_estimate;
```

**Result** (5 of 6 possible buckets returned — "4. On the estimated day" has 0 orders, confirming `delivery_delay_days = 0` essentially never occurs exactly):

| delivery_vs_estimate | n_orders | pct_of_delivered | cumulative_pct |
|---|---|---|---|
| 1. 15+ days ahead of estimate | 29,594 | 30.68% | 30.68% |
| 2. 7-14 days ahead of estimate | 41,709 | 43.24% | 73.91% |
| 3. 1-6 days ahead of estimate | 17,341 | 17.98% | 91.89% |
| 5. 1-7 days late | 4,481 | 4.64% | 96.53% |
| 6. 8+ days late | 3,345 | 3.47% | 100.00% |

**Key finding:** This is the most striking single number in the fulfillment domain: **73.91% of all deliveries arrive 7 or more days AHEAD of the promised date** (30.68% arrive 15+ days early!). Only **8.11%** of orders are late at all, and the "on-time, as-promised" middle ground (1-6 days ahead, or exactly on the day) is just 17.98%. **Olist is dramatically under-promising / over-padding its delivery estimates** — likely a deliberate strategy to protect against the long-tail variability seen in Q3.3 (transit p90 of 18.9 days vs median 7.1), but the cost is real: customers see a long "estimated delivery" window at checkout that may suppress conversion, even though actual performance is excellent. **The strategic tension this surfaces for an Amazon-style Ops/Pricing team**: tightening the estimate (e.g., from "15-25 days" to "10-15 days") would likely **increase the technical late-rate** (more orders would cross the promise threshold) but could **improve conversion** by showing customers a more attractive (and still mostly accurate) delivery promise — a classic "the metric we're optimizing (low late-rate) may be in tension with the metric that matters (conversion/satisfaction)" finding, exactly the kind of nuance a senior analyst is expected to surface rather than just reporting "late rate is low, good job."

---

### Q3.7: Did the Nov-2017 demand spike strain fulfillment?

**Business question:** Does a seasonal demand surge degrade delivery performance — i.e., does Operations capacity need to scale ahead of known seasonal peaks?

```sql
SELECT
    DATE_TRUNC('month', order_purchase_date)::date AS month,
    COUNT(*)                                        AS n_delivered,
    SUM(CASE WHEN is_late THEN 1 ELSE 0 END)        AS n_late,
    ROUND(100.0 * SUM(CASE WHEN is_late THEN 1 ELSE 0 END) / COUNT(*), 2) AS pct_late,
    ROUND(AVG(actual_delivery_days)::numeric, 2)    AS avg_actual_delivery_days,
    ROUND(AVG(delivery_delay_days)::numeric, 2)     AS avg_delay_days
FROM marts.fact_orders
WHERE is_delivered AND NOT dq_delivered_missing_date
  AND order_purchase_date BETWEEN '2017-09-01' AND '2018-01-31'
GROUP BY 1
ORDER BY 1;
```

**Result** (5 rows, Sep-2017 … Jan-2018):

| month | n_delivered | n_late | pct_late | avg_actual_delivery_days | avg_delay_days |
|---|---|---|---|---|---|
| 2017-09 | 4,150 | 216 | 5.20% | 11.85 | -10.59 |
| 2017-10 | 4,478 | 237 | 5.29% | 11.86 | -11.16 |
| **2017-11** | **7,288** | **1,043** | **14.31%** | **15.16** | **-7.40** |
| 2017-12 | 5,513 | 462 | 8.38% | 15.39 | -12.29 |
| 2018-01 | 7,069 | 464 | 6.56% | 14.08 | -12.22 |

**Key finding:** **Yes — directly and measurably.** The Nov-2017 Black Friday demand surge (+64% GMV vs trailing average, Q1.7; +53% order volume MoM, Q1.1) coincides with the late rate **nearly tripling** from a ~5.2% baseline (Sep/Oct) to **14.31%**, and `avg_actual_delivery_days` rising from ~11.9 to **15.16 days**. Notably, **Dec-2017 stays elevated** (15.39 days avg, the highest of the 5 months, though late-% partially recovers to 8.38% — likely because Dec orders' *estimates* were widened in anticipation) before fully normalizing by Jan-2018 (6.56% late). This is a clean **2-month "hangover" effect**: the Nov surge degrades both Nov and Dec performance before Jan returns near baseline. **For Operations planning**: this validates Q1.7's recommendation with hard fulfillment-metric evidence — **carrier/warehouse capacity should be scaled BEFORE the Black Friday surge** (e.g., temporary staffing, pre-positioned inventory, carrier contract surge clauses for late Nov), with the scale-up sustained through mid-December given the 2-month tail. Compare this "expected, recoverable" 2-month seasonal pattern against Q3.8's Feb-Mar 2018 anomaly, which is **larger and has no obvious demand-side trigger** — these are two different categories of risk requiring two different mitigations (capacity planning vs. root-cause investigation).

---

### Q3.8: Anomaly drill-down — the Feb-Mar 2018 OTD collapse

**Business question:** Q3.2 surfaced a much bigger and unexplained spike than the Nov-2017 one: monthly late rate jumped from ~7% (Jan-2018) to 16% (Feb-2018) to 21% (Mar-2018) — more than 2x the Black Friday effect. This query drills to **weekly** grain to pinpoint the window, then checks whether it's geographically broad (systemic) or concentrated in a few states (regional carrier issue).

```sql
SELECT
    DATE_TRUNC('week', order_purchase_date)::date AS week,
    COUNT(*)                                        AS n_delivered,
    SUM(CASE WHEN is_late THEN 1 ELSE 0 END)        AS n_late,
    ROUND(100.0 * SUM(CASE WHEN is_late THEN 1 ELSE 0 END) / COUNT(*), 2) AS pct_late,
    ROUND(AVG(actual_delivery_days)::numeric, 2)    AS avg_actual_delivery_days
FROM marts.fact_orders
WHERE is_delivered AND NOT dq_delivered_missing_date
  AND order_purchase_date BETWEEN '2018-01-15' AND '2018-04-15'
GROUP BY 1
ORDER BY 1;
```

**Result** (13 weeks, Jan 15 – Apr 9, 2018; peak weeks in **bold**):

| week of | n_delivered | n_late | pct_late | avg_actual_delivery_days |
|---|---|---|---|---|
| 2018-01-15 | 1,704 | 130 | 7.63% | 13.92 |
| 2018-01-22 | 1,545 | 130 | 8.41% | 14.18 |
| 2018-01-29 | 1,561 | 123 | 7.88% | 15.63 |
| 2018-02-05 | 1,541 | 149 | 9.67% | 16.58 |
| 2018-02-12 | 1,595 | 235 | 14.73% | 16.06 |
| **2018-02-19** | 1,713 | 365 | **21.31%** | 17.56 |
| **2018-02-26** | 1,849 | 536 | **28.99%** | 19.09 |
| **2018-03-05** | 1,598 | 442 | **27.66%** | 18.13 |
| 2018-03-12 | 1,541 | 356 | 23.10% | 16.78 |
| 2018-03-19 | 1,671 | 236 | 14.12% | 13.92 |
| 2018-03-26 | 1,431 | 193 | 13.49% | 13.89 |
| 2018-04-02 | 1,555 | 126 | 8.10% | 11.91 |
| 2018-04-09 | 1,522 | 61 | 4.01% | 11.58 |

**Finding:** the late rate climbs from ~8% (weeks of Jan 15 – Feb 5) to a **peak of 29.0% in the week of Feb 26** and 27.7% in the week of Mar 5, then recovers cleanly to ~4% by mid-April. `avg_actual_delivery_days` follows the same shape (13-14 days → 17-19 days → back to ~12 days). A state-level cut for the Feb-Mar 2018 window (not reproduced here in full — see `dashboard/extracts/anomaly_state_comparison.csv`) shows the spike hitting **10+ states across every region of Brazil** (CE, MA, AL, RJ, PA, MS, PI, ES, BA, SC all >24% late vs. their typical <16% from Q3.4) — i.e., **broad-based, not one regional carrier**.

**Hypothesis** (not verifiable from this dataset alone — flagged as a "would investigate with carrier-ops data" item, exactly the kind of root-cause question an Amazon Ops BA would be asked to chase): **Brazilian Carnival fell on Feb 10-14, 2018**. Orders placed in the 1-2 weeks around a national holiday that shuts down postal/carrier operations would sit in carrier backlog and arrive ~2 weeks later than normal — precisely the **Feb 19 – Mar 12** delivery window where the spike is concentrated. The clean recovery to baseline by April supports a **one-time backlog (cleared)** rather than a persistent capacity problem.

**Key finding:** This is the dataset's best example of an analyst going beyond "what happened" to "why, and what would I do about it." The pattern (broad-geographic, sharp-onset, clean-recovery, ~5-6 week duration, timed almost exactly to a known multi-day national holiday) is the **textbook signature of a holiday-driven carrier backlog**, not a systemic operations failure — which fundamentally changes the recommendation: **this is not primarily a "fix our logistics network" finding, it's a "build a Carnival-aware capacity/communication playbook" finding** (e.g., proactively widen delivery estimates for orders placed in the 2 weeks before Carnival, similar to how many retailers communicate "holiday shipping cutoffs"). If a future data extract confirms this recurs every Carnival (Brazil's Carnival date moves each year — Feb 10-14 in 2018, but e.g. early March in other years), this becomes a **predictable, schedulable annual mitigation** rather than a reactive fire-drill — directly analogous to how Amazon plans for Prime Day / Black Friday / Christmas surge capacity.

---

## Domain 4: Seller & Marketplace Performance
*(`sql/analytics/04_seller_marketplace.sql`)* — the Amazon Marketplace/3rd-party-seller lens: Olist is a marketplace aggregator, not a 1P retailer — 3,095 independent sellers list products that Olist provides order/payment/logistics infrastructure for. This domain covers revenue concentration across sellers (single-point-of-failure risk), seller-level service-quality scorecards, seller-base growth/maturity, the logistics cost of a geographically distributed seller base, and category-level competitive concentration (HHI).

**Attribution caveat** (applies to Q4.2): **97.97% of orders (97,388 / 99,441) contain items from a single seller.** For the 2.03% of multi-seller orders, order-level metrics (`review_score`, `is_late`) describe the *whole order*, not one seller's contribution specifically — an unavoidable grain mismatch in the source data. Q4.2's seller scorecard therefore treats these order-level metrics as a proxy for seller service quality, which is accurate for the large majority of orders but should not be read as a precise per-seller attribution for every row.

### Q4.1: Seller revenue concentration (Pareto) by decile

**Business question:** How reliant is total marketplace GMV on a small number of high-volume sellers — is there a single-point-of-failure risk if a top seller exits the platform?

```sql
-- Seller revenue concentration (Pareto) by decile
WITH seller_rev AS (
    SELECT
        seller_id,
        COUNT(DISTINCT order_id) AS n_orders,
        SUM(price)               AS revenue
    FROM marts.fact_order_items
    GROUP BY 1
),
deciles AS (
    SELECT
        seller_id, n_orders, revenue,
        NTILE(10) OVER (ORDER BY revenue DESC) AS revenue_decile
    FROM seller_rev
)
SELECT
    revenue_decile,
    COUNT(*)                                                   AS n_sellers,
    SUM(n_orders)                                              AS total_orders,
    ROUND(SUM(revenue)::numeric, 2)                            AS decile_revenue,
    ROUND(100.0 * SUM(revenue) / SUM(SUM(revenue)) OVER (), 2) AS pct_of_total_revenue,
    ROUND(100.0 * SUM(SUM(revenue)) OVER (ORDER BY revenue_decile)
          / SUM(SUM(revenue)) OVER (), 2)                      AS cumulative_pct_of_revenue
FROM deciles
GROUP BY revenue_decile
ORDER BY revenue_decile;
```

**Result** (10 rows = all sellers with ≥1 item, split into deciles by revenue; 3,095 sellers total):

| revenue_decile | n_sellers | total_orders | decile_revenue | pct_of_total_revenue | cumulative_pct |
|---|---|---|---|---|---|
| 1 (top) | 310 | 60,888 | R$9,183,174.76 | 67.56% | 67.56% |
| 2 | 310 | 16,359 | R$2,060,449.46 | 15.16% | 82.72% |
| 3 | 310 | 9,349 | R$1,033,680.10 | 7.61% | 90.33% |
| 4 | 310 | 4,737 | R$550,185.15 | 4.05% | 94.38% |
| 5 | 310 | 3,104 | R$328,923.78 | 2.42% | 96.80% |
| 6 | 309 | 2,069 | R$202,310.26 | 1.49% | 98.29% |
| 7 | 309 | 1,581 | R$116,479.44 | 0.86% | 99.14% |
| 8 | 309 | 893 | R$66,790.33 | 0.49% | 99.63% |
| 9 | 309 | 627 | R$36,032.70 | 0.27% | 99.90% |
| 10 (bottom) | 309 | 403 | R$13,617.72 | 0.10% | 100.00% |

**Methodology note:** This query uses `marts.fact_order_items` directly (all order items, regardless of order status), giving total seller-side revenue of **R$13,591,643.70**. The dashboard extract `seller_pareto_deciles.csv` applies the project's standard "valid orders" filter (`order_status NOT IN ('canceled','unavailable')`), giving a very slightly lower top-decile figure (R$9,108,736.71 / 67.50% / 306 sellers vs. this query's R$9,183,174.76 / 67.56% / 310 sellers). The ~0.7pp difference is fully explained by item revenue belonging to canceled/unavailable orders' top sellers — both numbers tell the same story; this catalog uses the unfiltered, item-grain figure since it answers "how much of the platform's transacted volume runs through top sellers" most directly, while the dashboard extract answers "how much of *completed-sale* revenue."

**Key finding:** **The top 10% of sellers (310 of 3,095) generate 67.56% of all marketplace revenue**, and the top 20% (620 sellers) account for **82.72%** — a textbook Pareto/power-law distribution, even more skewed than the customer-side concentration in Q2.5 (top 30% of customers = 64.68% of revenue). The bottom 50% of sellers (1,546 sellers, deciles 6-10) collectively contribute just **3.21%** of revenue — many of these are likely small, occasional, or single-SKU sellers. **For an Amazon Marketplace-strategy analyst, this is the headline marketplace-health metric**: a platform this dependent on its top decile has real concentration risk (losing even 2-3 of the largest sellers — examined individually in Q4.2 — could materially dent GMV), but it also represents an **opportunity**: the "long tail" of 1,546 low-revenue sellers is a large pool of accounts that could be activated with seller-success programs (the kind of seller-engagement initiative an Amazon Seller Services team would own).

---

### Q4.2: Top-20 seller performance scorecard

**Business question:** Are the highest-revenue sellers also high-quality (good candidates for promotion/featured placement), or is revenue concentrated in sellers with service problems that represent a risk to fix?

```sql
-- Top-20 sellers by revenue, with order volume, review score, and OTD scorecard
WITH seller_orders AS (
    SELECT
        oi.seller_id,
        oi.order_id,
        SUM(oi.price) AS item_revenue
    FROM marts.fact_order_items oi
    GROUP BY 1, 2
),
seller_order_quality AS (
    SELECT
        so.seller_id,
        so.order_id,
        so.item_revenue,
        fo.review_score,
        fo.is_delivered,
        fo.is_late,
        fo.dq_delivered_missing_date
    FROM seller_orders so
    JOIN marts.fact_orders fo ON fo.order_id = so.order_id
)
SELECT
    seller_id,
    COUNT(*)                                  AS n_orders,
    ROUND(SUM(item_revenue)::numeric, 2)      AS revenue,
    ROUND(AVG(item_revenue)::numeric, 2)      AS avg_revenue_per_order,
    ROUND(AVG(review_score)::numeric, 2)      AS avg_review_score,
    SUM(CASE WHEN is_delivered AND NOT dq_delivered_missing_date THEN 1 ELSE 0 END) AS n_delivered,
    ROUND(100.0 * SUM(CASE WHEN is_delivered AND NOT dq_delivered_missing_date AND is_late THEN 1 ELSE 0 END)
          / NULLIF(SUM(CASE WHEN is_delivered AND NOT dq_delivered_missing_date THEN 1 ELSE 0 END), 0), 2) AS pct_late
FROM seller_order_quality
GROUP BY seller_id
ORDER BY revenue DESC
LIMIT 20;
```

**Result** (20 rows; `seller_id` truncated to 8 chars for display — full IDs in `dashboard/extracts/seller_scorecard.csv`):

| seller_id | n_orders | revenue | avg_rev_per_order | avg_review_score | n_delivered | pct_late |
|---|---|---|---|---|---|---|
| 4869f7a5… | 1,132 | R$229,472.63 | R$202.71 | 4.13 | 1,124 | 11.57% |
| 53243585… | 358 | R$222,776.05 | R$622.28 | 4.13 | 348 | 4.31% |
| 4a3ca931… | 1,806 | R$200,472.92 | R$111.00 | 3.83 | 1,772 | 11.00% |
| fa1c13f2… | 585 | R$194,042.03 | R$331.70 | 4.34 | 578 | 10.21% |
| 7c67e144… | 982 | R$187,923.89 | R$191.37 | 3.49 | 973 | 10.07% |
| 7e93a43e… | 336 | R$176,431.87 | R$525.09 | 4.21 | 319 | 5.64% |
| da8622b1… | 1,314 | R$160,236.57 | R$121.95 | 4.18 | 1,311 | 7.63% |
| 7a67c85e… | 1,160 | R$141,745.53 | R$122.19 | 4.25 | 1,145 | 5.94% |
| 1025f0e2… | 915 | R$138,968.55 | R$151.88 | 3.99 | 910 | 10.11% |
| 955fee92… | 1,287 | R$135,171.70 | R$105.03 | 4.16 | 1,261 | 7.77% |
| 46dc3b2c… | 521 | R$128,111.19 | R$245.89 | 4.19 | 503 | 6.56% |
| 6560211a… | 1,854 | R$123,304.83 | R$66.51 | 3.93 | 1,819 | 6.43% |
| 620c87c1… | 740 | R$114,774.50 | R$155.10 | 4.25 | 722 | 9.97% |
| 7d13fca1… | 565 | R$113,628.97 | R$201.11 | 4.02 | 558 | 12.19% |
| 5dceca12… | 325 | R$112,155.53 | R$345.09 | 3.98 | 322 | 6.21% |
| 1f50f920… | 1,404 | R$106,939.21 | R$76.17 | 4.13 | 1,399 | 10.58% |
| cc419e06… | 1,706 | R$104,288.42 | R$61.13 | 4.07 | 1,651 | 6.12% |
| a1043baf… | 718 | R$101,901.16 | R$141.92 | 4.22 | 702 | 5.70% |
| 3d871de0… | 1,080 | R$94,914.20 | R$87.88 | 4.15 | 1,064 | 5.92% |
| edb1ef5e… | 166 | R$79,284.55 | R$477.62 | 4.42 | 165 | 7.88% |

**Key finding:** The top 20 sellers (0.65% of the 3,095-seller base) generate **R$2,866,544.30 — about 21.1% of total marketplace revenue** — confirming Q4.1's Pareto pattern is not just a decile-level abstraction but concentrated in a genuinely small number of named accounts. **Quality is reassuringly solid but not uniform**: avg_review_score across the top 20 ranges from **3.49** (`7c67e144…`, also tied for the highest late rate at 10.07%) to **4.42** (`edb1ef5e…`, smallest of the top 20 by volume at 166 orders). **`pct_late` is the more actionable quality signal** — 6 of the 20 top sellers (`4869f7a5…` 11.57%, `4a3ca931…` 11.00%, `fa1c13f2…` 10.21%, `7c67e144…` 10.07%, `1f50f920…` 10.58%, `7d13fca1…` 12.19%) run **late rates above 10%**, roughly double the platform's non-anomaly-month baseline of 3-8% (Q3.2) — and per Q3.5, crossing into the "4-7 days late" bucket alone drops average review score from 4.30 to 2.32. These 6 sellers collectively represent over R$1M in revenue and are the **highest-leverage targets for a seller-success/logistics-support intervention** — fixing their fulfillment timeliness would protect a disproportionate share of GMV from review-score collapse. Also notable: **`avg_revenue_per_order` spans nearly 10x** (R$61.13 to R$622.28) within this top-20 group — two fundamentally different marketplace business models (high-frequency/low-ticket vs. low-frequency/high-ticket) both scale to similar revenue, useful context for any seller-segmentation work.

---

### Q4.3: Seller acquisition and activity trend

**Business question:** Is the supply side (seller base) growing fast enough to support demand growth (Domain 1), or is GMV growth concentrating onto the existing seller base as the marketplace matures?

```sql
-- Monthly active sellers, new-seller acquisition, and cumulative onboarding
WITH seller_first_sale AS (
    SELECT seller_id, MIN(order_purchase_date) AS first_sale_date
    FROM marts.fact_order_items
    GROUP BY 1
),
monthly_active AS (
    SELECT
        DATE_TRUNC('month', order_purchase_date)::date AS month,
        COUNT(DISTINCT seller_id) AS active_sellers
    FROM marts.fact_order_items
    WHERE order_purchase_date BETWEEN '2017-01-01' AND '2018-08-31'
    GROUP BY 1
),
monthly_new AS (
    SELECT
        DATE_TRUNC('month', first_sale_date)::date AS month,
        COUNT(*) AS new_sellers
    FROM seller_first_sale
    WHERE first_sale_date BETWEEN '2017-01-01' AND '2018-08-31'
    GROUP BY 1
)
SELECT
    ma.month,
    ma.active_sellers,
    COALESCE(mn.new_sellers, 0)                                       AS new_sellers,
    SUM(COALESCE(mn.new_sellers, 0)) OVER (ORDER BY ma.month)         AS cumulative_sellers_onboarded,
    ROUND(100.0 * COALESCE(mn.new_sellers, 0) / ma.active_sellers, 2) AS new_seller_pct_of_active
FROM monthly_active ma
LEFT JOIN monthly_new mn ON mn.month = ma.month
ORDER BY ma.month;
```

**Result** (20 rows, 2017-01 .. 2018-08 — same analysis window as Domain 1):

| month | active_sellers | new_sellers | cumulative_onboarded | new_seller_pct_of_active |
|---|---|---|---|---|
| 2017-01 | 227 | 151 | 151 | 66.52% |
| 2017-02 | 427 | 228 | 379 | 53.40% |
| 2017-03 | 499 | 173 | 552 | 34.67% |
| 2017-04 | 506 | 116 | 668 | 22.92% |
| 2017-05 | 583 | 124 | 792 | 21.27% |
| 2017-06 | 539 | 76 | 868 | 14.10% |
| 2017-07 | 606 | 115 | 983 | 18.98% |
| 2017-08 | 708 | 129 | 1,112 | 18.22% |
| 2017-09 | 731 | 127 | 1,239 | 17.37% |
| 2017-10 | 776 | 147 | 1,386 | 18.94% |
| 2017-11 | 965 | 190 | 1,576 | 19.69% |
| 2017-12 | 861 | 90 | 1,666 | 10.45% |
| 2018-01 | 970 | 141 | 1,807 | 14.54% |
| 2018-02 | 947 | 120 | 1,927 | 12.67% |
| 2018-03 | 996 | 113 | 2,040 | 11.35% |
| 2018-04 | 1,123 | 202 | 2,242 | 17.99% |
| 2018-05 | 1,115 | 172 | 2,414 | 15.43% |
| 2018-06 | 1,175 | 191 | 2,605 | 16.26% |
| 2018-07 | 1,261 | 190 | 2,795 | 15.07% |
| 2018-08 | 1,278 | 155 | 2,950 | 12.13% |

**Key finding:** The seller base grew **5.6x** (227 → 1,278 active sellers/month) over the analysis window, while monthly delivered order volume grew **~8.5x** (750 → 6,351, Q3.2) — meaning order volume per active seller roughly grew too, from ~3.3 orders/seller/month (Jan-2017) to ~5.0 (Aug-2018). The clearest structural signal is `new_seller_pct_of_active`'s steady decline from **66.52% to 12.13%**: in early 2017 the *majority* of any month's active sellers were brand-new (consistent with this being the platform's early-growth phase), but by mid-2018 **roughly 7 in 8 active sellers in any given month had been selling for a while** — the marketplace has matured from an acquisition-led to a retention/engagement-led seller base. Two notable bumps interrupt the otherwise-smooth decline: **Nov-2017 (19.69%)**, coinciding with the Black Friday demand surge (Q1.7/Q3.7) — plausibly extra seller recruitment ahead of peak season — and **Apr-2018 (17.99%)**, just after the Feb-Mar fulfillment crisis (Q3.8), perhaps reflecting recovery-period onboarding. **Strategically**: the seller-growth curve is healthy and roughly tracks demand, but the *decelerating new-seller share* combined with Q1.1/Q1.2's flattening 2018 GMV plateau suggests the marketplace's next growth lever is less "onboard more sellers" and more "grow existing sellers' assortment/volume" — exactly the kind of seller-success account-management strategy question an Amazon Marketplace BA would be asked to model.

---

### Q4.4: Same-state vs. cross-state freight cost and transit time

**Business question:** What is the logistics cost/time penalty of Olist's distributed-seller model when sellers and customers are in different states — the common case, given seller supply is concentrated in SP (Q4.5) while demand is nationwide (Q2.6)?

```sql
-- Same-state vs. cross-state item-level freight % and shipping transit time
WITH item_geo AS (
    SELECT
        oi.order_id,
        oi.order_item_id,
        oi.price,
        oi.freight_value,
        ds.seller_state,
        fo.customer_state,
        fo.is_delivered,
        fo.dq_delivered_missing_date,
        fo.dq_delivered_before_carrier,
        fo.shipping_transit_days
    FROM marts.fact_order_items oi
    JOIN marts.dim_seller ds  ON ds.seller_id = oi.seller_id
    JOIN marts.fact_orders fo ON fo.order_id = oi.order_id
)
SELECT
    CASE WHEN seller_state = customer_state THEN '1. Same state' ELSE '2. Different state' END AS seller_customer_geo,
    COUNT(*)                                          AS n_items,
    ROUND(AVG(price)::numeric, 2)                     AS avg_item_price,
    ROUND(AVG(freight_value)::numeric, 2)             AS avg_freight_value,
    ROUND(100.0 * AVG(freight_value) / AVG(price), 2) AS freight_pct_of_price,
    ROUND(AVG(CASE WHEN is_delivered AND NOT dq_delivered_missing_date AND NOT dq_delivered_before_carrier
                   THEN shipping_transit_days END)::numeric, 2) AS avg_shipping_transit_days
FROM item_geo
GROUP BY 1
ORDER BY 1;
```

**Result** (2 rows, 112,650 total order items):

| seller_customer_geo | n_items | avg_item_price | avg_freight_value | freight_pct_of_price | avg_shipping_transit_days |
|---|---|---|---|---|---|
| 1. Same state | 40,756 | R$104.26 | R$13.46 | 12.91% | 4.75 |
| 2. Different state | 71,894 | R$129.95 | R$23.69 | 18.23% | 11.71 |

**Key finding:** **63.8% of all order items (71,894 of 112,650) ship cross-state** — a direct mathematical consequence of Q4.5's finding that 64.40% of seller supply sits in SP while Q2.6 shows demand spread across all 27 states. Cross-state items cost **76% more in freight in absolute terms** (R$23.69 vs. R$13.46, a R$10.23/item difference) and **41% more as a share of item price** (18.23% vs. 12.91%), and take **2.5x longer in transit** (11.71 vs. 4.75 days). This single table **explains two earlier findings simultaneously**: (1) Q3.4's observation that remote North/Northeast states have the longest absolute delivery times (19-27 days) — those customers are almost always served cross-state, often across the full length of the country; and (2) Q2.6's observation that those same remote states have AOV nearly **2x** SP's — `order_total_value` bundles `freight_value`, so the R$10.23/item cross-state freight premium directly inflates order value for exactly the customers who pay it. **For an Amazon-style fulfillment-network strategist**, the fix this points to is the classic marketplace playbook: **regional fulfillment/cross-dock hubs outside SP** (e.g., in PR/MG/RJ — Q4.5's #2-#4 supply states) would shorten the "different state" distance for a large share of cross-state shipments, directly attacking both the freight-cost gap and the transit-time gap in one investment.

---

### Q4.5: Seller supply concentration by state

**Business question:** Where is marketplace supply (sellers) physically located, and how does that compare to where demand (Q2.6: SP+RJ+MG = 62.51% of customer GMV) is concentrated?

```sql
-- Seller revenue, count, and cumulative share by seller state
WITH seller_state_agg AS (
    SELECT
        ds.seller_state,
        COUNT(DISTINCT oi.seller_id) AS n_sellers,
        COUNT(*)                     AS n_items,
        SUM(oi.price)                AS revenue
    FROM marts.fact_order_items oi
    JOIN marts.dim_seller ds ON ds.seller_id = oi.seller_id
    GROUP BY 1
)
SELECT
    seller_state,
    n_sellers,
    n_items,
    ROUND(revenue::numeric, 2)                                                AS revenue,
    ROUND(100.0 * revenue / SUM(revenue) OVER (), 2)                          AS pct_of_total_revenue,
    ROUND(100.0 * SUM(revenue) OVER (ORDER BY revenue DESC) / SUM(revenue) OVER (), 2) AS cumulative_pct,
    RANK() OVER (ORDER BY revenue DESC)                                       AS revenue_rank
FROM seller_state_agg
ORDER BY revenue DESC;
```

**Result** (23 of Brazil's 27 states have at least one seller; smallest 11 collapsed for brevity — full table in `dashboard/extracts/geo_seller_state_summary.csv`):

| rank | seller_state | n_sellers | n_items | revenue | pct_of_total | cumulative_pct |
|---|---|---|---|---|---|---|
| 1 | SP | 1,849 | 80,342 | R$8,753,396.21 | 64.40% | 64.40% |
| 2 | PR | 349 | 8,671 | R$1,261,887.21 | 9.28% | 73.69% |
| 3 | MG | 244 | 8,827 | R$1,011,564.74 | 7.44% | 81.13% |
| 4 | RJ | 171 | 4,818 | R$843,984.22 | 6.21% | 87.34% |
| 5 | SC | 190 | 4,075 | R$632,426.07 | 4.65% | 91.99% |
| 6 | RS | 129 | 2,199 | R$378,559.54 | 2.79% | 94.78% |
| 7 | BA | 19 | 643 | R$285,561.56 | 2.10% | 96.88% |
| 8 | DF | 30 | 899 | R$97,749.48 | 0.72% | 97.60% |
| 9 | PE | 9 | 448 | R$91,493.85 | 0.67% | 98.27% |
| 10 | GO | 40 | 520 | R$66,399.21 | 0.49% | 98.76% |
| 11 | ES | 23 | 372 | R$47,689.61 | 0.35% | 99.11% |
| 12 | MA | 1 | 405 | R$36,408.95 | 0.27% | 99.38% |
| 13-23 | CE, PB, MT, RN, MS, RO, PI, SE, PA, AM, AC | 1-13 each | ≤145 each | R$267-20,240 | ≤0.15% | 99.38%→100.00% |

**Key finding:** Seller supply is **even more geographically concentrated than customer demand**: a single state, **SP, holds 64.40% of marketplace revenue with 1,849 of 3,095 sellers (59.7%)** — compare to Q2.6 where it took **three** states (SP+RJ+MG) to reach 62.51% of *demand*. The top-5 supply states (SP, PR, MG, RJ, SC — all in Brazil's South/Southeast) account for **91.99%** of seller revenue; everything outside the top 12 (12 states combined) contributes well under 1%, and **several states have essentially no seller presence at all** (MA has exactly 1 seller; CE, AC, AM, PA, PI, SE each have 1-2). **The strategic read for an Amazon Marketplace/Seller-Recruitment analyst**: this is a **supply-side white-space map**. The states with negligible seller presence (Northeast/North Brazil) are precisely the states Q2.6 identified as having the **highest AOV** (PB, AC, AP, AL, PA, all ~R$220-265) and Q3.4 showed have the **best on-time-delivery rates relative to estimate** — i.e., there is *demand* and the *logistics promise* already works well there, but almost *no local supply*. A targeted seller-recruitment campaign in 2-3 Northeast hub cities could simultaneously (a) reduce the cross-state freight/transit penalty quantified in Q4.4 for that region's customers, and (b) capture more of the high-AOV demand currently being served (expensively) from 1,000+ km away.

---

### Q4.6: Marketplace concentration risk (HHI) in top-5 categories

**Business question:** Within the platform's 5 biggest-revenue categories (Q1.4), is the seller base fragmented (healthy competition) or dominated by 1-2 sellers (a concentration risk where that seller's exit would meaningfully disrupt category supply)?

```sql
-- HHI (Herfindahl-Hirschman Index, 0-10,000 scale) of seller revenue share
-- within each of the top-5 revenue categories.
-- Thresholds (US DOJ/FTC merger-guideline convention, used here as a generic
-- concentration yardstick): <1,500 unconcentrated, 1,500-2,500 moderately
-- concentrated, >2,500 highly concentrated.
WITH top_categories AS (
    SELECT dp.product_category_name_english AS category
    FROM marts.fact_order_items fi
    JOIN marts.dim_product dp ON dp.product_id = fi.product_id
    GROUP BY 1
    ORDER BY SUM(fi.price) DESC
    LIMIT 5
),
cat_seller_rev AS (
    SELECT
        dp.product_category_name_english AS category,
        fi.seller_id,
        SUM(fi.price) AS revenue
    FROM marts.fact_order_items fi
    JOIN marts.dim_product dp ON dp.product_id = fi.product_id
    WHERE dp.product_category_name_english IN (SELECT category FROM top_categories)
    GROUP BY 1, 2
),
shares AS (
    SELECT
        category,
        seller_id,
        revenue / SUM(revenue) OVER (PARTITION BY category) AS market_share
    FROM cat_seller_rev
)
SELECT
    category,
    COUNT(*)                                           AS n_sellers,
    ROUND(MAX(market_share) * 100, 2)                  AS top_seller_share_pct,
    ROUND(SUM(market_share * market_share) * 10000, 1) AS hhi,
    CASE
        WHEN SUM(market_share * market_share) * 10000 > 2500 THEN 'Highly concentrated'
        WHEN SUM(market_share * market_share) * 10000 > 1500 THEN 'Moderately concentrated'
        ELSE 'Unconcentrated'
    END AS concentration_level
FROM shares
GROUP BY category
ORDER BY hhi DESC;
```

**Result** (5 rows = Q1.4's top-5 revenue categories):

| category | n_sellers | top_seller_share_pct | hhi | concentration_level |
|---|---|---|---|---|
| watches_gifts | 101 | 16.69% | 931.4 | Unconcentrated |
| bed_bath_table | 196 | 15.93% | 599.8 | Unconcentrated |
| health_beauty | 492 | 6.30% | 235.7 | Unconcentrated |
| computers_accessories | 287 | 5.84% | 224.2 | Unconcentrated |
| sports_leisure | 481 | 5.47% | 150.4 | Unconcentrated |

**Key finding:** **Every one of the platform's top-5 revenue categories is "Unconcentrated" by the DOJ/FTC HHI yardstick** (all HHI < 1,500, the threshold for "moderately concentrated"). `watches_gifts` is the closest to a concentration concern — 101 sellers, but the top seller alone holds **16.69%** of category revenue (HHI 931.4) — still comfortably unconcentrated, but worth a watch-list flag if that seller's share grew further. At the other extreme, `health_beauty` (492 sellers, top share 6.30%, HHI 235.7) and `sports_leisure` (481 sellers, top share 5.47%, HHI 150.4) are **extremely fragmented**, healthy categories with no single-seller dependency at all. **This is an important nuance for the overall marketplace-concentration narrative**: Q4.1 showed the *seller base as a whole* is highly Pareto-concentrated (top decile = 67.56% of revenue) and Q4.5 showed *supply geography* is highly concentrated (SP = 64.40%) — but **within the categories that matter most for revenue, no single seller has cornered the market**. In other words, the concentration risk identified elsewhere in this domain is a **geographic and seller-roster** risk (a regional disruption or a handful of top accounts churning), not a **category-supply** risk (no category would lose its entire assortment if one seller left). An Amazon Marketplace-health dashboard should track both flavors of concentration separately, since they call for different mitigations (seller diversification by region vs. category-level seller recruitment).

---
