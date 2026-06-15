-- ============================================================================
-- STAGING LAYER
-- One model per raw source (dbt-CTAS style): type-cast, trim/normalize text,
-- deduplicate, and surface data-quality flags. No business logic / joins
-- across subject areas yet - that happens in marts.
-- ============================================================================

CREATE SCHEMA IF NOT EXISTS staging;

-- ----------------------------------------------------------------------------
-- stg_orders: pass-through with trimmed status. order_id verified unique in raw.
-- ----------------------------------------------------------------------------
DROP TABLE IF EXISTS staging.stg_orders CASCADE;
CREATE TABLE staging.stg_orders AS
SELECT
    order_id,
    customer_id,
    LOWER(TRIM(order_status))              AS order_status,
    order_purchase_timestamp,
    order_approved_at,
    order_delivered_carrier_date,
    order_delivered_customer_date,
    order_estimated_delivery_date,
    -- Data-quality flag: 'delivered' orders should have a delivered_customer_date.
    (LOWER(TRIM(order_status)) = 'delivered'
        AND order_delivered_customer_date IS NULL)  AS dq_delivered_missing_date
FROM raw.orders;

-- ----------------------------------------------------------------------------
-- stg_customers: trim/normalize geography text. Grain = customer_id (one row
-- per order's customer record). customer_unique_id identifies the real person
-- and is deduplicated in marts.dim_customer.
-- ----------------------------------------------------------------------------
DROP TABLE IF EXISTS staging.stg_customers CASCADE;
CREATE TABLE staging.stg_customers AS
SELECT
    customer_id,
    customer_unique_id,
    customer_zip_code_prefix,
    LOWER(TRIM(customer_city))   AS customer_city,
    UPPER(TRIM(customer_state))  AS customer_state
FROM raw.customers;

-- ----------------------------------------------------------------------------
-- stg_sellers: trim/normalize geography text.
-- ----------------------------------------------------------------------------
DROP TABLE IF EXISTS staging.stg_sellers CASCADE;
CREATE TABLE staging.stg_sellers AS
SELECT
    seller_id,
    seller_zip_code_prefix,
    LOWER(TRIM(seller_city))   AS seller_city,
    UPPER(TRIM(seller_state))  AS seller_state
FROM raw.sellers;

-- ----------------------------------------------------------------------------
-- stg_geolocation: raw has ~1M rows but only ~19K distinct zip prefixes, with
-- inconsistent city/state spellings per zip. Deduplicate to one row per zip:
-- average lat/lng (centroid) + the most frequently reported city/state.
-- ----------------------------------------------------------------------------
DROP TABLE IF EXISTS staging.stg_geolocation CASCADE;
CREATE TABLE staging.stg_geolocation AS
WITH city_state_counts AS (
    SELECT
        geolocation_zip_code_prefix AS zip_code_prefix,
        LOWER(TRIM(geolocation_city))  AS city,
        UPPER(TRIM(geolocation_state)) AS state,
        COUNT(*) AS n,
        ROW_NUMBER() OVER (
            PARTITION BY geolocation_zip_code_prefix
            ORDER BY COUNT(*) DESC
        ) AS rn
    FROM raw.geolocation
    GROUP BY 1, 2, 3
),
centroids AS (
    SELECT
        geolocation_zip_code_prefix AS zip_code_prefix,
        AVG(geolocation_lat) AS latitude,
        AVG(geolocation_lng) AS longitude,
        COUNT(*) AS n_pings
    FROM raw.geolocation
    GROUP BY 1
)
SELECT
    c.zip_code_prefix,
    csc.city,
    csc.state,
    c.latitude,
    c.longitude,
    c.n_pings
FROM centroids c
JOIN city_state_counts csc
    ON csc.zip_code_prefix = c.zip_code_prefix AND csc.rn = 1;

-- ----------------------------------------------------------------------------
-- stg_products: attach English category names. Two categories present in
-- products are missing from the translation table (manually mapped below);
-- products with a NULL category, or a category with no translation, fall
-- back to 'unknown'. Also derive package volume for logistics analysis.
-- ----------------------------------------------------------------------------
DROP TABLE IF EXISTS staging.stg_products CASCADE;
CREATE TABLE staging.stg_products AS
SELECT
    p.product_id,
    COALESCE(p.product_category_name, 'unknown') AS product_category_name,
    COALESCE(
        t.product_category_name_english,
        CASE p.product_category_name
            WHEN 'portateis_cozinha_e_preparadores_de_alimentos' THEN 'kitchen_portables_and_food_prep'
            WHEN 'pc_gamer' THEN 'pc_gamer'
            ELSE NULL
        END,
        'unknown'
    ) AS product_category_name_english,
    p.product_name_lenght        AS product_name_length,
    p.product_description_lenght AS product_description_length,
    p.product_photos_qty,
    p.product_weight_g,
    p.product_length_cm,
    p.product_height_cm,
    p.product_width_cm,
    (p.product_length_cm * p.product_height_cm * p.product_width_cm) AS product_volume_cm3,
    (p.product_category_name IS NULL) AS dq_category_missing
FROM raw.products p
LEFT JOIN raw.product_category_translation t
    ON p.product_category_name = t.product_category_name;

-- ----------------------------------------------------------------------------
-- stg_order_items: pass-through with non-negative price/freight validation.
-- ----------------------------------------------------------------------------
DROP TABLE IF EXISTS staging.stg_order_items CASCADE;
CREATE TABLE staging.stg_order_items AS
SELECT
    order_id,
    order_item_id,
    product_id,
    seller_id,
    shipping_limit_date,
    price,
    freight_value,
    (price < 0 OR freight_value < 0) AS dq_negative_amount
FROM raw.order_items;

-- ----------------------------------------------------------------------------
-- stg_order_payments: pass-through with non-negative value validation.
-- ----------------------------------------------------------------------------
DROP TABLE IF EXISTS staging.stg_order_payments CASCADE;
CREATE TABLE staging.stg_order_payments AS
SELECT
    order_id,
    payment_sequential,
    LOWER(TRIM(payment_type)) AS payment_type,
    payment_installments,
    payment_value,
    (payment_value < 0) AS dq_negative_amount
FROM raw.order_payments;

-- ----------------------------------------------------------------------------
-- stg_order_reviews: 547 orders have 2-3 review rows and 789 review_ids are
-- duplicated. Deduplicate to one review per order_id, keeping the most
-- recently created review (ties broken by review_answer_timestamp), and flag
-- orders that originally had multiple reviews.
-- ----------------------------------------------------------------------------
DROP TABLE IF EXISTS staging.stg_order_reviews CASCADE;
CREATE TABLE staging.stg_order_reviews AS
WITH ranked AS (
    SELECT
        review_id,
        order_id,
        review_score,
        review_comment_title,
        review_comment_message,
        review_creation_date,
        review_answer_timestamp,
        COUNT(*) OVER (PARTITION BY order_id) AS n_reviews_for_order,
        ROW_NUMBER() OVER (
            PARTITION BY order_id
            ORDER BY review_creation_date DESC, review_answer_timestamp DESC, review_id
        ) AS rn
    FROM raw.order_reviews
)
SELECT
    review_id,
    order_id,
    review_score,
    review_comment_title,
    review_comment_message,
    review_creation_date,
    review_answer_timestamp,
    (n_reviews_for_order > 1) AS dq_had_multiple_reviews
FROM ranked
WHERE rn = 1;
