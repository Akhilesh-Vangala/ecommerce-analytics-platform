-- ============================================================================
-- MARTS LAYER - FACTS
-- ============================================================================

-- ----------------------------------------------------------------------------
-- fact_orders: grain = 1 row per order. Aggregates items/payments/review to
-- the order level and derives every fulfillment-timing metric used by the
-- Operations-lens analytics (carrier handoff, transit time, delivery delay).
--
-- delivery_delay_days > 0  -> delivered AFTER the estimate (late)
-- delivery_delay_days < 0  -> delivered BEFORE the estimate (early)
--
-- Redshift: DISTKEY (customer_unique_id) - co-locates a customer's orders for
-- fast RFM/cohort joins to dim_customer; SORTKEY (order_purchase_date) - the
-- dominant range-filter/group-by column across all analytics queries.
-- ----------------------------------------------------------------------------
DROP TABLE IF EXISTS marts.fact_orders CASCADE;
CREATE TABLE marts.fact_orders AS
WITH item_agg AS (
    SELECT
        order_id,
        COUNT(*)                       AS n_items,
        COUNT(DISTINCT product_id)     AS n_distinct_products,
        COUNT(DISTINCT seller_id)      AS n_distinct_sellers,
        SUM(price)                     AS items_price_total,
        SUM(freight_value)             AS freight_value_total
    FROM staging.stg_order_items
    GROUP BY order_id
),
payment_agg AS (
    SELECT
        order_id,
        SUM(payment_value)                                  AS payment_value_total,
        MAX(payment_installments)                           AS max_installments,
        COUNT(DISTINCT payment_type)                        AS n_payment_types,
        (ARRAY_AGG(payment_type ORDER BY payment_value DESC))[1] AS primary_payment_type
    FROM staging.stg_order_payments
    GROUP BY order_id
)
SELECT
    o.order_id,
    c.customer_unique_id,
    c.customer_zip_code_prefix,
    c.customer_state,
    o.order_status,
    o.order_purchase_timestamp,
    o.order_purchase_timestamp::date AS order_purchase_date,
    o.order_approved_at,
    o.order_delivered_carrier_date,
    o.order_delivered_customer_date,
    o.order_estimated_delivery_date,

    COALESCE(ia.n_items, 0)             AS n_items,
    ia.n_distinct_products,
    ia.n_distinct_sellers,
    COALESCE(ia.items_price_total, 0)   AS items_price_total,
    COALESCE(ia.freight_value_total, 0) AS freight_value_total,
    COALESCE(ia.items_price_total, 0) + COALESCE(ia.freight_value_total, 0) AS order_total_value,

    pa.payment_value_total,
    pa.max_installments,
    pa.n_payment_types,
    pa.primary_payment_type,

    r.review_score,
    (r.review_id IS NOT NULL) AS has_review,

    -- Timing metrics (fractional days unless noted)
    EXTRACT(EPOCH FROM (o.order_approved_at - o.order_purchase_timestamp)) / 3600.0          AS approval_hours,
    EXTRACT(EPOCH FROM (o.order_delivered_carrier_date - o.order_approved_at)) / 86400.0     AS carrier_handoff_days,
    EXTRACT(EPOCH FROM (o.order_delivered_customer_date - o.order_delivered_carrier_date)) / 86400.0 AS shipping_transit_days,
    EXTRACT(EPOCH FROM (o.order_delivered_customer_date - o.order_purchase_timestamp)) / 86400.0     AS actual_delivery_days,
    EXTRACT(EPOCH FROM (o.order_estimated_delivery_date - o.order_purchase_timestamp)) / 86400.0     AS estimated_delivery_days,
    EXTRACT(EPOCH FROM (o.order_delivered_customer_date - o.order_estimated_delivery_date)) / 86400.0 AS delivery_delay_days,

    (o.order_status = 'delivered')                                                            AS is_delivered,
    (o.order_status = 'delivered'
        AND o.order_delivered_customer_date > o.order_estimated_delivery_date)                AS is_late,
    (o.order_status = 'canceled')                                                              AS is_canceled,
    o.dq_delivered_missing_date,

    -- Source-data timestamp anomalies (~1.4% / ~0.02% of orders): the
    -- recorded carrier-handoff or customer-delivery event precedes the prior
    -- step. Rows are kept (revenue/review still valid) but flagged so
    -- fulfillment-timing KPIs (carrier_handoff_days, shipping_transit_days)
    -- can exclude them - see sql/analytics/03_fulfillment_ops.sql.
    (o.order_delivered_carrier_date IS NOT NULL AND o.order_approved_at IS NOT NULL
        AND o.order_delivered_carrier_date < o.order_approved_at)                              AS dq_carrier_before_approval,
    (o.order_delivered_customer_date IS NOT NULL AND o.order_delivered_carrier_date IS NOT NULL
        AND o.order_delivered_customer_date < o.order_delivered_carrier_date)                  AS dq_delivered_before_carrier
FROM staging.stg_orders o
JOIN staging.stg_customers c ON c.customer_id = o.customer_id
LEFT JOIN item_agg ia    ON ia.order_id = o.order_id
LEFT JOIN payment_agg pa ON pa.order_id = o.order_id
LEFT JOIN staging.stg_order_reviews r ON r.order_id = o.order_id;

ALTER TABLE marts.fact_orders ADD PRIMARY KEY (order_id);
CREATE INDEX idx_fact_orders_purchase_date  ON marts.fact_orders (order_purchase_date);
CREATE INDEX idx_fact_orders_customer       ON marts.fact_orders (customer_unique_id);
CREATE INDEX idx_fact_orders_state          ON marts.fact_orders (customer_state);
ALTER TABLE marts.fact_orders
    ADD CONSTRAINT fk_fact_orders_customer
    FOREIGN KEY (customer_unique_id) REFERENCES marts.dim_customer (customer_unique_id);
ALTER TABLE marts.fact_orders
    ADD CONSTRAINT fk_fact_orders_date
    FOREIGN KEY (order_purchase_date) REFERENCES marts.dim_date (date_day);

-- ----------------------------------------------------------------------------
-- fact_order_items: grain = 1 row per (order_id, order_item_id) - the
-- Retail-lens fact table for revenue/category/seller analysis.
-- Redshift: DISTKEY (order_id) - co-locates items with their order for joins
-- back to fact_orders; SORTKEY (order_purchase_date).
-- ----------------------------------------------------------------------------
DROP TABLE IF EXISTS marts.fact_order_items CASCADE;
CREATE TABLE marts.fact_order_items AS
SELECT
    oi.order_id,
    oi.order_item_id,
    oi.product_id,
    oi.seller_id,
    o.order_purchase_timestamp::date AS order_purchase_date,
    oi.price,
    oi.freight_value,
    (oi.price + oi.freight_value) AS item_total_value,
    oi.shipping_limit_date
FROM staging.stg_order_items oi
JOIN staging.stg_orders o ON o.order_id = oi.order_id;

ALTER TABLE marts.fact_order_items ADD PRIMARY KEY (order_id, order_item_id);
CREATE INDEX idx_fact_items_product ON marts.fact_order_items (product_id);
CREATE INDEX idx_fact_items_seller  ON marts.fact_order_items (seller_id);
CREATE INDEX idx_fact_items_date    ON marts.fact_order_items (order_purchase_date);
ALTER TABLE marts.fact_order_items
    ADD CONSTRAINT fk_fact_items_order
    FOREIGN KEY (order_id) REFERENCES marts.fact_orders (order_id);
ALTER TABLE marts.fact_order_items
    ADD CONSTRAINT fk_fact_items_product
    FOREIGN KEY (product_id) REFERENCES marts.dim_product (product_id);
ALTER TABLE marts.fact_order_items
    ADD CONSTRAINT fk_fact_items_seller
    FOREIGN KEY (seller_id) REFERENCES marts.dim_seller (seller_id);
ALTER TABLE marts.fact_order_items
    ADD CONSTRAINT fk_fact_items_date
    FOREIGN KEY (order_purchase_date) REFERENCES marts.dim_date (date_day);

-- ----------------------------------------------------------------------------
-- fact_order_payments: grain = 1 row per (order_id, payment_sequential) -
-- payment-method/installment-level detail (checkout behavior: installment
-- plans, voucher usage, split payments) that fact_orders' aggregates lose.
-- Redshift: DISTKEY (order_id), SORTKEY (order_purchase_date).
-- ----------------------------------------------------------------------------
DROP TABLE IF EXISTS marts.fact_order_payments CASCADE;
CREATE TABLE marts.fact_order_payments AS
SELECT
    p.order_id,
    p.payment_sequential,
    o.order_purchase_timestamp::date AS order_purchase_date,
    p.payment_type,
    p.payment_installments,
    p.payment_value
FROM staging.stg_order_payments p
JOIN staging.stg_orders o ON o.order_id = p.order_id;

ALTER TABLE marts.fact_order_payments ADD PRIMARY KEY (order_id, payment_sequential);
CREATE INDEX idx_fact_payments_type ON marts.fact_order_payments (payment_type);
CREATE INDEX idx_fact_payments_date ON marts.fact_order_payments (order_purchase_date);
ALTER TABLE marts.fact_order_payments
    ADD CONSTRAINT fk_fact_payments_order
    FOREIGN KEY (order_id) REFERENCES marts.fact_orders (order_id);
ALTER TABLE marts.fact_order_payments
    ADD CONSTRAINT fk_fact_payments_date
    FOREIGN KEY (order_purchase_date) REFERENCES marts.dim_date (date_day);
