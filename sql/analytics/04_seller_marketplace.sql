-- ============================================================================
-- DOMAIN 4: SELLER & MARKETPLACE PERFORMANCE (Amazon Marketplace lens)
--
-- Olist is a marketplace aggregator (Amazon's 3rd-party-seller model, not its
-- 1P retail model): 3,095 independent sellers list products that Olist
-- fulfills order/payment/logistics infrastructure for. This domain answers
-- the questions an Amazon Marketplace/Seller-Ops analyst owns: revenue
-- concentration across sellers, seller-level service quality (on-time
-- delivery, review score), seller acquisition/activity trends, and
-- cross-state logistics cost.
--
-- ATTRIBUTION CAVEAT: 97.97% of orders (97,388 / 99,441) contain items from a
-- single seller. For the 2.03% of multi-seller orders, fact_orders-level
-- metrics (review_score, is_late) describe the WHOLE ORDER, not one seller's
-- contribution specifically - an unavoidable grain mismatch in this dataset.
-- Q4.2's seller scorecard therefore treats these as a proxy for seller service
-- quality, accurate for the large majority of orders.
-- ============================================================================


-- ----------------------------------------------------------------------------
-- Q4.1: Seller revenue concentration (Pareto) by decile.
-- Business question: How reliant is total GMV on a small number of
-- high-volume sellers? (marketplace concentration / single-point-of-failure
-- risk)
-- ----------------------------------------------------------------------------
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
    COUNT(*)                                                            AS n_sellers,
    SUM(n_orders)                                                       AS total_orders,
    ROUND(SUM(revenue)::numeric, 2)                                     AS decile_revenue,
    ROUND(100.0 * SUM(revenue) / SUM(SUM(revenue)) OVER (), 2)          AS pct_of_total_revenue,
    ROUND(100.0 * SUM(SUM(revenue)) OVER (ORDER BY revenue_decile)
          / SUM(SUM(revenue)) OVER (), 2)                               AS cumulative_pct_of_revenue
FROM deciles
GROUP BY revenue_decile
ORDER BY revenue_decile;


-- ----------------------------------------------------------------------------
-- Q4.2: Top-20 sellers by revenue - performance scorecard (revenue, order
-- volume, avg review score, on-time delivery rate).
-- Business question: Are our highest-revenue sellers also high-quality
-- (good candidates for promotion/featured placement), or is revenue
-- concentrated in sellers with service problems (risk to address)?
-- ----------------------------------------------------------------------------
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


-- ----------------------------------------------------------------------------
-- Q4.3: Seller acquisition and activity trend - new sellers making their
-- first sale per month, monthly active sellers, and cumulative sellers
-- onboarded.
-- Business question: Is the supply side (seller base) growing fast enough to
-- support demand growth (Domain 1), or is GMV growth concentrating onto the
-- existing seller base?
-- ----------------------------------------------------------------------------
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


-- ----------------------------------------------------------------------------
-- Q4.4: Same-state vs. cross-state seller-customer pairs - freight cost and
-- shipping transit time.
-- Business question: What is the logistics cost/time penalty of Olist's
-- distributed-seller model when sellers and customers are in different
-- states (the common case, given seller supply is concentrated in
-- SP/PR/MG - Q4.5 - while demand is nationwide - Domain 2, Q2.6)?
-- ----------------------------------------------------------------------------
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
    COUNT(*)                                                AS n_items,
    ROUND(AVG(price)::numeric, 2)                           AS avg_item_price,
    ROUND(AVG(freight_value)::numeric, 2)                   AS avg_freight_value,
    ROUND(100.0 * AVG(freight_value) / AVG(price), 2)       AS freight_pct_of_price,
    ROUND(AVG(CASE WHEN is_delivered AND NOT dq_delivered_missing_date AND NOT dq_delivered_before_carrier
                   THEN shipping_transit_days END)::numeric, 2) AS avg_shipping_transit_days
FROM item_geo
GROUP BY 1
ORDER BY 1;


-- ----------------------------------------------------------------------------
-- Q4.5: Seller supply concentration by state - revenue, seller count, and
-- cumulative share.
-- Business question: Where is marketplace supply located, and how does that
-- compare to where demand is concentrated (Domain 2, Q2.6: SP/RJ/MG = 62.5%
-- of customer GMV)?
-- ----------------------------------------------------------------------------
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


-- ----------------------------------------------------------------------------
-- Q4.6: Marketplace concentration risk (Herfindahl-Hirschman Index) within
-- the top-5 revenue categories (from Domain 1, Q1.4).
-- Business question: In our biggest categories, is the seller base
-- fragmented (healthy competition) or dominated by one or two sellers
-- (concentration risk - a seller exit would meaningfully disrupt category
-- supply)? HHI (sum of squared market shares, 0-10,000 scale) is the
-- standard antitrust/competition metric: <1,500 = unconcentrated,
-- 1,500-2,500 = moderately concentrated, >2,500 = highly concentrated
-- (US DOJ/FTC merger guideline thresholds, used here as a generic
-- concentration yardstick).
-- ----------------------------------------------------------------------------
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
    COUNT(*)                                AS n_sellers,
    ROUND(MAX(market_share) * 100, 2)       AS top_seller_share_pct,
    ROUND(SUM(market_share * market_share) * 10000, 1) AS hhi,
    CASE
        WHEN SUM(market_share * market_share) * 10000 > 2500 THEN 'Highly concentrated'
        WHEN SUM(market_share * market_share) * 10000 > 1500 THEN 'Moderately concentrated'
        ELSE 'Unconcentrated'
    END AS concentration_level
FROM shares
GROUP BY category
ORDER BY hhi DESC;
