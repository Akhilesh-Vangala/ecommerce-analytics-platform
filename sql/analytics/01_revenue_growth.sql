-- ============================================================================
-- DOMAIN 1: REVENUE & GROWTH (Amazon Retail lens)
-- All queries exclude order_status IN ('canceled','unavailable') unless noted
-- - these orders never generated fulfilled revenue.
--
-- ANALYSIS WINDOW NOTE: raw order_purchase_date spans 2016-09 to 2018-10, but
-- 2016 has only 296 orders total (platform pilot/ramp-up) and Sep+Oct 2018
-- combined have just 20 orders (data extract cutoff mid-Sep). Trend queries
-- (Q1.1, Q1.2, Q1.7) use 2017-01 .. 2018-08 - the first full, comparable
-- 20-month window - so month-over-month % changes aren't dominated by
-- ramp-up/cutoff noise.
-- Q1.3 (YoY) further restricts to Jan-Aug for a clean 8-vs-8 month comparison.
-- ============================================================================


-- ----------------------------------------------------------------------------
-- Q1.1: Monthly GMV & order volume trend with month-over-month growth.
-- Business question: Is the marketplace growing, and how volatile is
-- month-to-month growth? (LAG window function for MoM %)
-- ----------------------------------------------------------------------------
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


-- ----------------------------------------------------------------------------
-- Q1.2: Cumulative GMV and 3-month rolling average GMV.
-- Business question: What is the underlying growth trend once monthly
-- noise/seasonality is smoothed out? (SUM/AVG OVER with frame clause)
-- ----------------------------------------------------------------------------
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


-- ----------------------------------------------------------------------------
-- Q1.3: Year-over-year comparison, Jan-Aug 2017 vs Jan-Aug 2018 (8 comparable
-- months each side).
-- Business question: How much did the business grow year-over-year on a
-- like-for-like basis?
-- ----------------------------------------------------------------------------
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


-- ----------------------------------------------------------------------------
-- Q1.4: Revenue concentration (Pareto) by product category.
-- Business question: How concentrated is revenue across categories - does a
-- small set of categories drive most of GMV? (window SUM for cumulative %)
-- ----------------------------------------------------------------------------
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


-- ----------------------------------------------------------------------------
-- Q1.5: Category mix shift, Jan-Aug 2017 vs Jan-Aug 2018 - which categories
-- are gaining/losing share of GMV?
-- Business question: Beyond overall growth, which categories are growing
-- faster/slower than the marketplace as a whole? (PARTITION BY for
-- period-relative share, then self-join to compare periods)
-- ----------------------------------------------------------------------------
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


-- ----------------------------------------------------------------------------
-- Q1.6: Top-3 best-selling products (by revenue) within each of the top-5
-- categories.
-- Business question: Within our highest-revenue categories, which specific
-- products should merchandising/inventory teams prioritize? (RANK with
-- PARTITION BY)
-- ----------------------------------------------------------------------------
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


-- ----------------------------------------------------------------------------
-- Q1.7: Seasonality - revenue by calendar month, flagging months that spike
-- well above their own recent trend (e.g. a Black-Friday-driven peak).
-- Business question: Is there a recurring seasonal pattern, and how large is
-- it relative to what the recent trend would predict?
--
-- METHODOLOGY NOTE: a naive "z-score vs. the full-period mean/stddev" approach
-- was tried first and flagged ZERO months - the strong underlying 2017->2018
-- growth trend inflates the overall stddev enough to mask the Nov-2017
-- Black Friday bump (z = 1.20, below the |z| > 2 threshold). The fix is to
-- de-trend first: compare each month to the average of its own trailing 3
-- months (LAG-based window, excluding the current month) rather than to a
-- single global average. This is the correct general pattern for seasonality
-- detection on a fast-growing series.
--
-- INTERPRETATION NOTE: with a 1.3x trailing-avg threshold, Feb-May 2017 also
-- flag as "spikes" - but that's platform ramp-up/hyper-growth (the trailing
-- average is still tiny in the first few months), not calendar seasonality,
-- and would not be expected to recur once the marketplace matures. Nov-2017
-- is the only spike during the post-ramp "mature" period (Jun-2017 onward,
-- where MoM growth has settled below ~25%) and lines up with Black Friday
-- (Nov 24, 2017 in Brazil) - this is the genuine recurring-seasonality signal.
-- A second Black Friday data point would require Nov-2018 data, which this
-- extract does not include (cutoff is Sep-2018).
-- ----------------------------------------------------------------------------
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
