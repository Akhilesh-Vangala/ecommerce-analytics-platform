# Data Quality Report

_Generated: 2026-06-14T10:49:24_

**Summary: 32 PASS / 0 FAIL / 7 INFO out of 39 checks**

> All assertion checks passed. INFO rows document known, handled data realities.

## Completeness

| Check | Status | Detail | Description |
|---|---|---|---|
| fact_order_items.product_id / seller_id not null | PASS | 0 null(s) | Every item must have a product and seller |
| fact_orders.customer_unique_id not null | PASS | 0 null(s) | Every order must resolve to a customer |
| fact_orders.order_purchase_timestamp not null | PASS | 0 null(s) | Every order must have a purchase timestamp |
| fact_orders.review_score null rate | INFO | 0.77% (768 orders) | Orders with no matching review row - expected, not all orders are reviewed |

## Data Quality Flags (Informational)

| Check | Status | Detail | Description |
|---|---|---|---|
| customer/seller zip prefixes with no geolocation match | INFO | 275 total (customers + sellers) | Zip prefix not present in Olist geolocation table - excluded from map visuals |
| orders that originally had multiple review rows | INFO | 547 | Deduplicated to most-recent review in staging.stg_order_reviews |
| orders where carrier handoff precedes approval | INFO | 1359 (1.37% of orders) | Flagged via dq_carrier_before_approval; excluded from carrier_handoff_days KPI averages |
| orders where customer delivery precedes carrier handoff | INFO | 23 (0.02% of orders) | Flagged via dq_delivered_before_carrier; excluded from shipping_transit_days KPI averages |
| orders with status=delivered but no delivered_customer_date | INFO | 8 | Source data anomaly - excluded from delivery-timing analysis via NULL handling |
| products with missing/unmapped category | INFO | 610 | Mapped to category "unknown" in staging.stg_products |

## Primary Key Uniqueness

| Check | Status | Detail | Description |
|---|---|---|---|
| marts.dim_customer.customer_unique_id | PASS | 0 duplicate(s) | customer_unique_id must be unique |
| marts.dim_geography.zip_code_prefix | PASS | 0 duplicate(s) | zip_code_prefix must be unique |
| marts.dim_product.product_id | PASS | 0 duplicate(s) | product_id must be unique |
| marts.dim_seller.seller_id | PASS | 0 duplicate(s) | seller_id must be unique |
| marts.fact_order_items (order_id, order_item_id) | PASS | 0 duplicate(s) | composite key must be unique |
| marts.fact_order_payments (order_id, payment_sequential) | PASS | 0 duplicate(s) | composite key must be unique |
| marts.fact_orders.order_id | PASS | 0 duplicate(s) | order_id must be unique |

## Referential Integrity

| Check | Status | Detail | Description |
|---|---|---|---|
| fact_order_items.order_id -> fact_orders | PASS | 0 orphan(s) | Every order item must belong to a known order |
| fact_order_items.product_id -> dim_product | PASS | 0 orphan(s) | Every order item must reference a known product |
| fact_order_items.seller_id -> dim_seller | PASS | 0 orphan(s) | Every order item must reference a known seller |
| fact_order_payments.order_id -> fact_orders | PASS | 0 orphan(s) | Every payment row must belong to a known order |
| fact_orders.customer_unique_id -> dim_customer | PASS | 0 orphan(s) | Every order must reference a known customer |

## Row Count Reconciliation

| Check | Status | Detail | Description |
|---|---|---|---|
| raw.customers -> staging.stg_customers | PASS | 99441 | Pass-through model must preserve row count (99,441) |
| raw.geolocation dedup -> staging.stg_geolocation | PASS | 19015 | Dedup to 1 row per distinct zip prefix (19,015) |
| raw.order_items -> staging.stg_order_items -> marts.fact_order_items | PASS | 112650 | Pass-through model + fact must preserve row count (112,650) |
| raw.order_payments -> staging.stg_order_payments -> marts.fact_order_payments | PASS | 103886 | Pass-through model + fact must preserve row count (103,886) |
| raw.order_reviews dedup -> staging.stg_order_reviews | PASS | 98673 | Dedup to 1 review per order_id (98,673) |
| raw.orders -> staging.stg_orders | PASS | 99441 | Pass-through model must preserve row count (99,441) |
| raw.products -> staging.stg_products | PASS | 32951 | Pass-through model must preserve row count (32,951) |
| raw.sellers -> staging.stg_sellers | PASS | 3095 | Pass-through model must preserve row count (3,095) |
| staging.stg_orders -> marts.fact_orders | PASS | 99441 | fact_orders grain = 1 row per order (99,441) |

## Temporal Consistency

| Check | Status | Detail | Description |
|---|---|---|---|
| dq_carrier_before_approval flags all carrier<approval rows | PASS | 0 unflagged violation(s) | Every carrier-before-approval row must be flagged for downstream exclusion |
| dq_delivered_before_carrier flags all delivered<carrier rows | PASS | 0 unflagged violation(s) | Every delivered-before-carrier row must be flagged for downstream exclusion |
| order_approved_at >= order_purchase_timestamp | PASS | 0 violation(s) | Approval cannot precede purchase |

## Value Range Validity

| Check | Status | Detail | Description |
|---|---|---|---|
| dim_product non-negative dimensions | PASS | 0 invalid row(s) | weight/length/height/width must be non-negative where present |
| order_items price/freight >= 0 | PASS | 0 negative row(s) | price and freight_value must be non-negative |
| order_payments payment_value >= 0 | PASS | 0 negative row(s) | payment_value must be non-negative |
| order_purchase_timestamp within [2016-01-01, 2018-12-31] | PASS | 0 out-of-range row(s) | Purchases must fall within the dim_date calendar spine |
| review_score in [1,5] or null | PASS | 0 out-of-range row(s) | review_score must be between 1 and 5 inclusive |
