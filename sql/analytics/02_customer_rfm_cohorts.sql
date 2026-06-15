-- ============================================================================
-- DOMAIN 2: CUSTOMER RFM & COHORT RETENTION (Amazon Retail lens)
-- All queries exclude order_status IN ('canceled','unavailable') unless noted
-- - these orders never generated fulfilled revenue.
--
-- HEADLINE STRUCTURAL FINDING (drives every query design choice below):
-- 93,099 of 96,096 customers (96.9%) place exactly ONE order ever; only 2,997
-- (3.1%) ever return. This is a well-documented characteristic of the Olist
-- marketplace (sellers are mostly small/regional, customers often buy a
-- one-off item and never return to that *specific seller's* catalog again -
-- unlike a single-brand retailer where repeat purchase is the norm).
--
-- Why this matters for an Amazon-style read of the data:
--   - Classic RFM "Frequency" and cohort "retention curves" are designed for
--     businesses where repeat purchase is common. Here, Frequency is
--     degenerate (96.9% tie at F=1), so a naive NTILE(5) on frequency would
--     mostly split ties arbitrarily. Q2.1 therefore segments on
--     Recency x Monetary, with repeat-purchase status layered on as a
--     separate flag rather than a third NTILE dimension.
--   - Cohort retention curves (Q2.3) will show ~2-3% month-1 retention across
--     EVERY cohort - not a sign of a broken query, but the central strategic
--     finding: this marketplace currently looks nothing like Amazon's
--     repeat-purchase/Prime-driven model, and GMV growth (Domain 1) is being
--     driven almost entirely by NEW customer acquisition (quantified in
--     Q2.4), not retention. That is precisely the kind of gap an Amazon
--     Retail BA would be expected to surface and act on (loyalty program,
--     post-purchase email/coupon, subscribe-and-save analogues).
-- ============================================================================


-- ----------------------------------------------------------------------------
-- Q2.1: RFM segmentation (Recency x Monetary quintiles; Frequency as a
-- separate repeat/one-time flag - see header note on why F is excluded from
-- the NTILE scoring).
-- Business question: Which customers are high-value-and-recent (nurture),
-- high-value-but-lapsed (win-back priority), or low-value (low priority)?
-- ----------------------------------------------------------------------------
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
        customer_unique_id,
        recency_days,
        frequency,
        monetary,
        NTILE(5) OVER (ORDER BY recency_days DESC) AS r_score,  -- 5 = most recent
        NTILE(5) OVER (ORDER BY monetary ASC)      AS m_score   -- 5 = highest spend
    FROM customer_rfm
)
SELECT
    r_score,
    m_score,
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


-- ----------------------------------------------------------------------------
-- Q2.2: Repeat-purchase rate and time-to-second-order for the 3.1% of
-- customers who ever return.
-- Business question: How rare is repeat purchase, and for those who do
-- return, how long does it take?
-- ----------------------------------------------------------------------------
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


-- ----------------------------------------------------------------------------
-- Q2.3: Acquisition-cohort retention curve, months 0-6 since first order.
-- Business question: Of customers acquired in month X, what % place ANOTHER
-- order in each of the following 6 months?
--
-- Cohort month is derived from each customer's first NON-CANCELED order
-- (not dim_customer.first_order_date, which includes canceled/unavailable
-- orders) so that month-0 retention is 100% by construction - the standard
-- cohort-analysis convention. This excludes 1,106 customers (1.2% of the
-- 96,096 in dim_customer) whose entire order history is canceled/unavailable
-- and who therefore never "joined" a revenue-generating cohort.
-- ----------------------------------------------------------------------------
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
    a.cohort_month,
    cs.cohort_customers,
    a.months_since_acquisition::int AS months_since_acquisition,
    COUNT(DISTINCT a.customer_unique_id) AS active_customers,
    ROUND(100.0 * COUNT(DISTINCT a.customer_unique_id) / cs.cohort_customers, 2) AS retention_pct
FROM activity a
JOIN cohort_size cs ON cs.cohort_month = a.cohort_month
WHERE a.months_since_acquisition BETWEEN 0 AND 6
  AND a.cohort_month BETWEEN '2017-01-01' AND '2018-02-01'  -- cohorts need >=6mo of follow-up data (extract ends 2018-10)
GROUP BY a.cohort_month, cs.cohort_customers, a.months_since_acquisition
ORDER BY a.cohort_month, a.months_since_acquisition;


-- ----------------------------------------------------------------------------
-- Q2.4: New vs. returning-customer share of monthly orders and GMV.
-- Business question: How much of our growth (Domain 1) is new-customer
-- acquisition vs. existing-customer reactivation?
-- order_seq is computed over EACH CUSTOMER'S FULL ORDER HISTORY (not just the
-- reporting window) so a 2017 order from a 2016-acquired customer is
-- correctly counted as "returning".
-- ----------------------------------------------------------------------------
WITH order_seq AS (
    SELECT
        order_id,
        customer_unique_id,
        order_purchase_date,
        order_total_value,
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


-- ----------------------------------------------------------------------------
-- Q2.5: Customer lifetime monetary value distribution and revenue
-- concentration by spend decile (Pareto on customers, not products/categories).
-- Business question: How much of total revenue depends on a small group of
-- high-spend customers?
-- ----------------------------------------------------------------------------
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
        customer_unique_id,
        total_spend,
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


-- ----------------------------------------------------------------------------
-- Q2.6: Customer geography - order volume, GMV, AOV and revenue concentration
-- by customer state.
-- Business question: Which states drive the marketplace, and where is AOV
-- meaningfully higher/lower than the national average (pricing/logistics
-- implications)?
-- ----------------------------------------------------------------------------
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
    customer_state,
    n_customers,
    n_orders,
    ROUND(gmv::numeric, 2)                                                AS gmv,
    ROUND((gmv / n_orders)::numeric, 2)                                   AS aov,
    ROUND(100.0 * gmv / SUM(gmv) OVER (), 2)                              AS pct_of_total_gmv,
    ROUND(100.0 * SUM(gmv) OVER (ORDER BY gmv DESC) / SUM(gmv) OVER (), 2) AS cumulative_pct_gmv,
    RANK() OVER (ORDER BY gmv DESC)                                       AS gmv_rank
FROM state_agg
ORDER BY gmv DESC;
