-- ============================================================================
-- DOMAIN 3: FULFILLMENT & OPERATIONS (Amazon Operations lens)
--
-- This domain maps onto the metrics an Amazon Operations/Fulfillment analyst
-- owns: order-to-delivery cycle time broken into stages (seller processing,
-- carrier handoff, line-haul/transit), promise-date ("estimated delivery
-- date") accuracy, on-time delivery rate (OTD) by geography and time, and the
-- downstream impact of late delivery on customer satisfaction (review score).
--
-- DQ-FLAG HANDLING: per docs/data_quality_report.md, 1.37% of orders have
-- order_delivered_carrier_date < order_approved_at (dq_carrier_before_approval)
-- and 0.02% have order_delivered_customer_date < order_delivered_carrier_date
-- (dq_delivered_before_carrier). These are source-data timestamp anomalies.
-- Every stage-timing query below excludes the affected rows from THAT STAGE's
-- average (the row's revenue/review data is still valid and used elsewhere).
-- ============================================================================


-- ----------------------------------------------------------------------------
-- Q3.1: Order status funnel - what share of all orders reach each terminal
-- status?
-- Business question: What % of demand converts to a completed delivery, and
-- how much is lost to cancellation/unavailability?
-- ----------------------------------------------------------------------------
SELECT
    order_status,
    COUNT(*) AS n_orders,
    ROUND(100.0 * COUNT(*) / SUM(COUNT(*)) OVER (), 2) AS pct_of_orders
FROM marts.fact_orders
GROUP BY 1
ORDER BY n_orders DESC;


-- ----------------------------------------------------------------------------
-- Q3.2: Monthly on-time delivery rate (OTD) and average delivery cycle time,
-- with month-over-month change in OTD (LAG window function).
-- Business question: Is delivery performance improving, holding steady, or
-- degrading as order volume grows?
-- ----------------------------------------------------------------------------
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
    month,
    n_delivered,
    n_late,
    ROUND(100.0 * n_late / n_delivered, 2) AS pct_late,
    ROUND(avg_actual_days::numeric, 2)     AS avg_actual_delivery_days,
    ROUND(avg_delay_days::numeric, 2)      AS avg_delay_days,
    ROUND((100.0 * n_late / n_delivered
           - LAG(100.0 * n_late / n_delivered) OVER (ORDER BY month))::numeric, 2) AS pct_late_pp_mom_change
FROM monthly
ORDER BY month;


-- ----------------------------------------------------------------------------
-- Q3.3: Fulfillment cycle-time stage breakdown (mean / median / p90), with
-- DQ-anomaly rows excluded per stage as documented above.
-- Business question: Where does time go between purchase and delivery -
-- seller processing (approval->carrier), carrier pickup-to-delivery (transit),
-- or overall? Which stage has the heaviest right tail (p90)?
-- ----------------------------------------------------------------------------
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


-- ----------------------------------------------------------------------------
-- Q3.4: On-time delivery rate by customer state, ranked worst-to-best
-- (RANK window function). States with < 30 delivered orders are excluded -
-- their OTD% would be statistically unstable.
-- Business question: Which delivery regions need carrier/logistics
-- intervention, and how does delivery time scale with distance from the
-- SP/RJ/MG core (Domain 2, Q2.6)?
-- ----------------------------------------------------------------------------
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
    customer_state,
    n_delivered,
    n_late,
    ROUND(100.0 * n_late / n_delivered, 2)   AS pct_late,
    ROUND(avg_actual_days::numeric, 2)       AS avg_actual_delivery_days,
    ROUND(avg_delay_days::numeric, 2)        AS avg_delay_days,
    RANK() OVER (ORDER BY 100.0 * n_late / n_delivered DESC) AS worst_otd_rank
FROM state_perf
ORDER BY pct_late DESC;


-- ----------------------------------------------------------------------------
-- Q3.5: Delivery-delay bucket vs. review score.
-- Business question: How strongly does a late delivery hurt customer
-- satisfaction, and at what delay threshold does the damage accelerate?
-- (Full statistical hypothesis test of this relationship is in the Python
-- EDA phase - this is the descriptive SQL-level cut.)
-- ----------------------------------------------------------------------------
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


-- ----------------------------------------------------------------------------
-- Q3.6: Estimated-delivery-date accuracy distribution.
-- Business question: How well-calibrated is Olist's delivery promise? Is the
-- platform over-promising (frequent lateness) or under-promising (padding
-- estimates, which hurts conversion even when delivery is "on time")?
-- ----------------------------------------------------------------------------
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


-- ----------------------------------------------------------------------------
-- Q3.7: Did the Nov-2017 demand spike (Domain 1, Q1.7: +64% GMV vs trailing
-- 3-month average) strain fulfillment? On-time delivery rate and average
-- delivery time, Sep-2017 through Jan-2018.
-- Business question: Does a seasonal demand surge degrade delivery
-- performance - i.e., does Operations capacity need to scale ahead of known
-- seasonal peaks?
-- ----------------------------------------------------------------------------
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


-- ----------------------------------------------------------------------------
-- Q3.8: ANOMALY DRILL-DOWN - the Feb-Mar 2018 OTD collapse.
-- Q3.2 showed monthly late rate jumping from ~7% (Jan-2018) to 16% (Feb) to
-- 21% (Mar), more than 2x the Nov-2017 Black Friday effect. This drills to
-- weekly grain to find the exact window and checks whether it's systemic or
-- a regional carrier issue.
--
-- FINDING: late rate climbs from ~8% (Jan 15-Feb 5) to a peak of 29.0% in the
-- week of Feb 26 and 27.7% in the week of Mar 5, recovering to ~4% by
-- mid-April. avg_actual_delivery_days follows the same shape (13-14 days ->
-- ~17-19 days -> ~12 days). The state-level cut shows 10+ states across
-- every region above 24% late (vs. their typical <16% from Q3.4), so this is
-- broad-based, not one regional carrier.
--
-- HYPOTHESIS (unverifiable from this dataset alone, would need carrier-ops
-- data to confirm): Brazilian Carnival fell on Feb 10-14, 2018. A national
-- holiday that shuts down postal/carrier operations would push orders placed
-- in the surrounding 1-2 weeks into a backlog, arriving ~2 weeks later than
-- normal - which lines up with the Feb 19-Mar 12 delivery window where the
-- spike is concentrated. The clean recovery by April supports a one-time
-- backlog rather than a persistent capacity problem.
-- ----------------------------------------------------------------------------
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
