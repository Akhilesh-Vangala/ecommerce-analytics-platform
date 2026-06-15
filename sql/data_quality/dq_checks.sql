-- ============================================================================
-- DATA QUALITY CHECK SUITE
-- Every check returns (category, check_name, status, detail, description).
-- status is PASS/FAIL for assertions, INFO for descriptive metrics that are
-- expected to be non-zero (documented data-quality realities, not bugs).
-- Run via etl/run_dq_checks.py, which renders a markdown report.
-- ============================================================================

-- ---------------------------------------------------------------------------
-- 1. ROW COUNT RECONCILIATION (raw -> staging, pass-through models)
-- ---------------------------------------------------------------------------
SELECT 'Row Count Reconciliation' AS category, 'raw.orders -> staging.stg_orders' AS check_name,
       CASE WHEN (SELECT COUNT(*) FROM raw.orders) = (SELECT COUNT(*) FROM staging.stg_orders) THEN 'PASS' ELSE 'FAIL' END AS status,
       (SELECT COUNT(*) FROM staging.stg_orders)::text AS detail,
       'Pass-through model must preserve row count (99,441)' AS description

UNION ALL SELECT 'Row Count Reconciliation', 'raw.customers -> staging.stg_customers',
       CASE WHEN (SELECT COUNT(*) FROM raw.customers) = (SELECT COUNT(*) FROM staging.stg_customers) THEN 'PASS' ELSE 'FAIL' END,
       (SELECT COUNT(*) FROM staging.stg_customers)::text, 'Pass-through model must preserve row count (99,441)'

UNION ALL SELECT 'Row Count Reconciliation', 'raw.sellers -> staging.stg_sellers',
       CASE WHEN (SELECT COUNT(*) FROM raw.sellers) = (SELECT COUNT(*) FROM staging.stg_sellers) THEN 'PASS' ELSE 'FAIL' END,
       (SELECT COUNT(*) FROM staging.stg_sellers)::text, 'Pass-through model must preserve row count (3,095)'

UNION ALL SELECT 'Row Count Reconciliation', 'raw.products -> staging.stg_products',
       CASE WHEN (SELECT COUNT(*) FROM raw.products) = (SELECT COUNT(*) FROM staging.stg_products) THEN 'PASS' ELSE 'FAIL' END,
       (SELECT COUNT(*) FROM staging.stg_products)::text, 'Pass-through model must preserve row count (32,951)'

UNION ALL SELECT 'Row Count Reconciliation', 'raw.order_items -> staging.stg_order_items -> marts.fact_order_items',
       CASE WHEN (SELECT COUNT(*) FROM raw.order_items) = (SELECT COUNT(*) FROM staging.stg_order_items)
             AND (SELECT COUNT(*) FROM staging.stg_order_items) = (SELECT COUNT(*) FROM marts.fact_order_items)
            THEN 'PASS' ELSE 'FAIL' END,
       (SELECT COUNT(*) FROM marts.fact_order_items)::text, 'Pass-through model + fact must preserve row count (112,650)'

UNION ALL SELECT 'Row Count Reconciliation', 'raw.order_payments -> staging.stg_order_payments -> marts.fact_order_payments',
       CASE WHEN (SELECT COUNT(*) FROM raw.order_payments) = (SELECT COUNT(*) FROM staging.stg_order_payments)
             AND (SELECT COUNT(*) FROM staging.stg_order_payments) = (SELECT COUNT(*) FROM marts.fact_order_payments)
            THEN 'PASS' ELSE 'FAIL' END,
       (SELECT COUNT(*) FROM marts.fact_order_payments)::text, 'Pass-through model + fact must preserve row count (103,886)'

UNION ALL SELECT 'Row Count Reconciliation', 'staging.stg_orders -> marts.fact_orders',
       CASE WHEN (SELECT COUNT(*) FROM staging.stg_orders) = (SELECT COUNT(*) FROM marts.fact_orders) THEN 'PASS' ELSE 'FAIL' END,
       (SELECT COUNT(*) FROM marts.fact_orders)::text, 'fact_orders grain = 1 row per order (99,441)'

UNION ALL SELECT 'Row Count Reconciliation', 'raw.geolocation dedup -> staging.stg_geolocation',
       CASE WHEN (SELECT COUNT(DISTINCT geolocation_zip_code_prefix) FROM raw.geolocation) = (SELECT COUNT(*) FROM staging.stg_geolocation) THEN 'PASS' ELSE 'FAIL' END,
       (SELECT COUNT(*) FROM staging.stg_geolocation)::text, 'Dedup to 1 row per distinct zip prefix (19,015)'

UNION ALL SELECT 'Row Count Reconciliation', 'raw.order_reviews dedup -> staging.stg_order_reviews',
       CASE WHEN (SELECT COUNT(DISTINCT order_id) FROM raw.order_reviews) = (SELECT COUNT(*) FROM staging.stg_order_reviews) THEN 'PASS' ELSE 'FAIL' END,
       (SELECT COUNT(*) FROM staging.stg_order_reviews)::text, 'Dedup to 1 review per order_id (98,673)'

-- ---------------------------------------------------------------------------
-- 2. PRIMARY KEY UNIQUENESS (marts layer)
-- ---------------------------------------------------------------------------
UNION ALL SELECT 'Primary Key Uniqueness', 'marts.fact_orders.order_id',
       CASE WHEN COUNT(*) = COUNT(DISTINCT order_id) THEN 'PASS' ELSE 'FAIL' END,
       (COUNT(*) - COUNT(DISTINCT order_id))::text || ' duplicate(s)', 'order_id must be unique'
FROM marts.fact_orders

UNION ALL SELECT 'Primary Key Uniqueness', 'marts.fact_order_items (order_id, order_item_id)',
       CASE WHEN COUNT(*) = COUNT(DISTINCT (order_id, order_item_id)) THEN 'PASS' ELSE 'FAIL' END,
       (COUNT(*) - COUNT(DISTINCT (order_id, order_item_id)))::text || ' duplicate(s)', 'composite key must be unique'
FROM marts.fact_order_items

UNION ALL SELECT 'Primary Key Uniqueness', 'marts.dim_customer.customer_unique_id',
       CASE WHEN COUNT(*) = COUNT(DISTINCT customer_unique_id) THEN 'PASS' ELSE 'FAIL' END,
       (COUNT(*) - COUNT(DISTINCT customer_unique_id))::text || ' duplicate(s)', 'customer_unique_id must be unique'
FROM marts.dim_customer

UNION ALL SELECT 'Primary Key Uniqueness', 'marts.dim_product.product_id',
       CASE WHEN COUNT(*) = COUNT(DISTINCT product_id) THEN 'PASS' ELSE 'FAIL' END,
       (COUNT(*) - COUNT(DISTINCT product_id))::text || ' duplicate(s)', 'product_id must be unique'
FROM marts.dim_product

UNION ALL SELECT 'Primary Key Uniqueness', 'marts.dim_seller.seller_id',
       CASE WHEN COUNT(*) = COUNT(DISTINCT seller_id) THEN 'PASS' ELSE 'FAIL' END,
       (COUNT(*) - COUNT(DISTINCT seller_id))::text || ' duplicate(s)', 'seller_id must be unique'
FROM marts.dim_seller

UNION ALL SELECT 'Primary Key Uniqueness', 'marts.dim_geography.zip_code_prefix',
       CASE WHEN COUNT(*) = COUNT(DISTINCT zip_code_prefix) THEN 'PASS' ELSE 'FAIL' END,
       (COUNT(*) - COUNT(DISTINCT zip_code_prefix))::text || ' duplicate(s)', 'zip_code_prefix must be unique'
FROM marts.dim_geography

UNION ALL SELECT 'Primary Key Uniqueness', 'marts.fact_order_payments (order_id, payment_sequential)',
       CASE WHEN COUNT(*) = COUNT(DISTINCT (order_id, payment_sequential)) THEN 'PASS' ELSE 'FAIL' END,
       (COUNT(*) - COUNT(DISTINCT (order_id, payment_sequential)))::text || ' duplicate(s)', 'composite key must be unique'
FROM marts.fact_order_payments

-- ---------------------------------------------------------------------------
-- 3. COMPLETENESS (nulls in critical columns)
-- ---------------------------------------------------------------------------
UNION ALL SELECT 'Completeness', 'fact_orders.customer_unique_id not null',
       CASE WHEN COUNT(*) - COUNT(customer_unique_id) = 0 THEN 'PASS' ELSE 'FAIL' END,
       (COUNT(*) - COUNT(customer_unique_id))::text || ' null(s)', 'Every order must resolve to a customer'
FROM marts.fact_orders

UNION ALL SELECT 'Completeness', 'fact_orders.order_purchase_timestamp not null',
       CASE WHEN COUNT(*) - COUNT(order_purchase_timestamp) = 0 THEN 'PASS' ELSE 'FAIL' END,
       (COUNT(*) - COUNT(order_purchase_timestamp))::text || ' null(s)', 'Every order must have a purchase timestamp'
FROM marts.fact_orders

UNION ALL SELECT 'Completeness', 'fact_order_items.product_id / seller_id not null',
       CASE WHEN COUNT(*) - COUNT(product_id) = 0 AND COUNT(*) - COUNT(seller_id) = 0 THEN 'PASS' ELSE 'FAIL' END,
       ((COUNT(*) - COUNT(product_id)) + (COUNT(*) - COUNT(seller_id)))::text || ' null(s)', 'Every item must have a product and seller'
FROM marts.fact_order_items

UNION ALL SELECT 'Completeness', 'fact_orders.review_score null rate',
       'INFO',
       ROUND(100.0 * (COUNT(*) - COUNT(review_score)) / COUNT(*), 2)::text || '% (' || (COUNT(*) - COUNT(review_score))::text || ' orders)',
       'Orders with no matching review row - expected, not all orders are reviewed'
FROM marts.fact_orders

-- ---------------------------------------------------------------------------
-- 4. VALUE RANGE VALIDITY
-- ---------------------------------------------------------------------------
UNION ALL SELECT 'Value Range Validity', 'review_score in [1,5] or null',
       CASE WHEN COUNT(*) = 0 THEN 'PASS' ELSE 'FAIL' END,
       COUNT(*)::text || ' out-of-range row(s)', 'review_score must be between 1 and 5 inclusive'
FROM marts.fact_orders WHERE review_score IS NOT NULL AND (review_score < 1 OR review_score > 5)

UNION ALL SELECT 'Value Range Validity', 'order_items price/freight >= 0',
       CASE WHEN COUNT(*) = 0 THEN 'PASS' ELSE 'FAIL' END,
       COUNT(*)::text || ' negative row(s)', 'price and freight_value must be non-negative'
FROM staging.stg_order_items WHERE dq_negative_amount

UNION ALL SELECT 'Value Range Validity', 'order_payments payment_value >= 0',
       CASE WHEN COUNT(*) = 0 THEN 'PASS' ELSE 'FAIL' END,
       COUNT(*)::text || ' negative row(s)', 'payment_value must be non-negative'
FROM staging.stg_order_payments WHERE dq_negative_amount

UNION ALL SELECT 'Value Range Validity', 'order_purchase_timestamp within [2016-01-01, 2018-12-31]',
       CASE WHEN COUNT(*) = 0 THEN 'PASS' ELSE 'FAIL' END,
       COUNT(*)::text || ' out-of-range row(s)', 'Purchases must fall within the dim_date calendar spine'
FROM marts.fact_orders
WHERE order_purchase_date < '2016-01-01' OR order_purchase_date > '2018-12-31'

UNION ALL SELECT 'Value Range Validity', 'dim_product non-negative dimensions',
       CASE WHEN COUNT(*) = 0 THEN 'PASS' ELSE 'FAIL' END,
       COUNT(*)::text || ' invalid row(s)', 'weight/length/height/width must be non-negative where present'
FROM marts.dim_product
WHERE product_weight_g < 0 OR product_length_cm < 0 OR product_height_cm < 0 OR product_width_cm < 0

-- ---------------------------------------------------------------------------
-- 5. REFERENTIAL INTEGRITY (enforced by FK constraints; checked explicitly too)
-- ---------------------------------------------------------------------------
UNION ALL SELECT 'Referential Integrity', 'fact_order_items.order_id -> fact_orders',
       CASE WHEN COUNT(*) = 0 THEN 'PASS' ELSE 'FAIL' END,
       COUNT(*)::text || ' orphan(s)', 'Every order item must belong to a known order'
FROM marts.fact_order_items fi LEFT JOIN marts.fact_orders fo ON fo.order_id = fi.order_id WHERE fo.order_id IS NULL

UNION ALL SELECT 'Referential Integrity', 'fact_order_items.product_id -> dim_product',
       CASE WHEN COUNT(*) = 0 THEN 'PASS' ELSE 'FAIL' END,
       COUNT(*)::text || ' orphan(s)', 'Every order item must reference a known product'
FROM marts.fact_order_items fi LEFT JOIN marts.dim_product dp ON dp.product_id = fi.product_id WHERE dp.product_id IS NULL

UNION ALL SELECT 'Referential Integrity', 'fact_order_items.seller_id -> dim_seller',
       CASE WHEN COUNT(*) = 0 THEN 'PASS' ELSE 'FAIL' END,
       COUNT(*)::text || ' orphan(s)', 'Every order item must reference a known seller'
FROM marts.fact_order_items fi LEFT JOIN marts.dim_seller ds ON ds.seller_id = fi.seller_id WHERE ds.seller_id IS NULL

UNION ALL SELECT 'Referential Integrity', 'fact_orders.customer_unique_id -> dim_customer',
       CASE WHEN COUNT(*) = 0 THEN 'PASS' ELSE 'FAIL' END,
       COUNT(*)::text || ' orphan(s)', 'Every order must reference a known customer'
FROM marts.fact_orders fo LEFT JOIN marts.dim_customer dc ON dc.customer_unique_id = fo.customer_unique_id WHERE dc.customer_unique_id IS NULL

UNION ALL SELECT 'Referential Integrity', 'fact_order_payments.order_id -> fact_orders',
       CASE WHEN COUNT(*) = 0 THEN 'PASS' ELSE 'FAIL' END,
       COUNT(*)::text || ' orphan(s)', 'Every payment row must belong to a known order'
FROM marts.fact_order_payments fp LEFT JOIN marts.fact_orders fo ON fo.order_id = fp.order_id WHERE fo.order_id IS NULL

-- ---------------------------------------------------------------------------
-- 6. TEMPORAL CONSISTENCY
-- carrier-before-approval and delivered-before-carrier are real source-data
-- anomalies (not derivation bugs) - they are flagged on fact_orders rather
-- than asserted away. The checks here assert the FLAGS correctly capture
-- every anomalous row (a flag-correctness check), which is what should hold
-- by construction.
-- ---------------------------------------------------------------------------
UNION ALL SELECT 'Temporal Consistency', 'order_approved_at >= order_purchase_timestamp',
       CASE WHEN COUNT(*) = 0 THEN 'PASS' ELSE 'FAIL' END,
       COUNT(*)::text || ' violation(s)', 'Approval cannot 
       
FROM marts.fact_orders WHERE order_approved_at IS NOT NULL AND order_approved_at < order_purchase_timestamp

UNION ALL SELECT 'Temporal Consistency', 'dq_carrier_before_approval flags all carrier<approval rows',
       CASE WHEN COUNT(*) = 0 THEN 'PASS' ELSE 'FAIL' END,
       COUNT(*)::text || ' unflagged violation(s)', 'Every carrier-before-approval row must be flagged for downstream exclusion'
FROM marts.fact_orders
WHERE order_delivered_carrier_date IS NOT NULL AND order_approved_at IS NOT NULL
  AND order_delivered_carrier_date < order_approved_at AND NOT dq_carrier_before_approval

UNION ALL SELECT 'Temporal Consistency', 'dq_delivered_before_carrier flags all delivered<carrier rows',
       CASE WHEN COUNT(*) = 0 THEN 'PASS' ELSE 'FAIL' END,
       COUNT(*)::text || ' unflagged violation(s)', 'Every delivered-before-carrier row must be flagged for downstream exclusion'
FROM marts.fact_orders
WHERE order_delivered_customer_date IS NOT NULL AND order_delivered_carrier_date IS NOT NULL
  AND order_delivered_customer_date < order_delivered_carrier_date AND NOT dq_delivered_before_carrier

-- ---------------------------------------------------------------------------
-- 7. DATA QUALITY FLAGS (informational - documented realities of the source data)
-- ---------------------------------------------------------------------------
UNION ALL SELECT 'Data Quality Flags (Informational)', 'orders with status=delivered but no delivered_customer_date',
       'INFO', COUNT(*)::text, 'Source data anomaly - excluded from delivery-timing analysis via NULL handling'
FROM marts.fact_orders WHERE dq_delivered_missing_date

UNION ALL SELECT 'Data Quality Flags (Informational)', 'orders where carrier handoff precedes approval',
       'INFO', COUNT(*)::text || ' (' || ROUND(100.0*COUNT(*)/(SELECT COUNT(*) FROM marts.fact_orders), 2)::text || '% of orders)',
       'Flagged via dq_carrier_before_approval; excluded from carrier_handoff_days KPI averages'
FROM marts.fact_orders WHERE dq_carrier_before_approval

UNION ALL SELECT 'Data Quality Flags (Informational)', 'orders where customer delivery precedes carrier handoff',
       'INFO', COUNT(*)::text || ' (' || ROUND(100.0*COUNT(*)/(SELECT COUNT(*) FROM marts.fact_orders), 2)::text || '% of orders)',
       'Flagged via dq_delivered_before_carrier; excluded from shipping_transit_days KPI averages'
FROM marts.fact_orders WHERE dq_delivered_before_carrier

UNION ALL SELECT 'Data Quality Flags (Informational)', 'products with missing/unmapped category',
       'INFO', COUNT(*)::text, 'Mapped to category "unknown" in staging.stg_products'
FROM marts.dim_product WHERE dq_category_missing

UNION ALL SELECT 'Data Quality Flags (Informational)', 'orders that originally had multiple review rows',
       'INFO', COUNT(*)::text, 'Deduplicated to most-recent review in staging.stg_order_reviews'
FROM staging.stg_order_reviews WHERE dq_had_multiple_reviews

UNION ALL SELECT 'Data Quality Flags (Informational)', 'customer/seller zip prefixes with no geolocation match',
       'INFO',
       ((SELECT COUNT(*) FROM marts.dim_customer WHERE customer_latitude IS NULL)
        + (SELECT COUNT(*) FROM marts.dim_seller WHERE seller_latitude IS NULL))::text || ' total (customers + sellers)',
       'Zip prefix not present in Olist geolocation table - excluded from map visuals'

ORDER BY category, check_name;
