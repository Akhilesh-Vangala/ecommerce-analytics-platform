-- ============================================================================
-- MARTS LAYER - DIMENSIONS
-- Star schema, analysis-ready. Redshift notes: dimension tables here are all
-- small (<100K rows) -> DISTSTYLE ALL (broadcast to every node) is the
-- Redshift-recommended choice, so every join to a fact table is local.
-- See redshift/DEPLOYMENT.md for the full Redshift DDL variant.
-- ============================================================================

CREATE SCHEMA IF NOT EXISTS marts;

-- ----------------------------------------------------------------------------
-- dim_date: calendar spine, Jan 2016 - Dec 2018 (covers full order +
-- delivery + estimate date range with a buffer for cohort/seasonality work).
-- Redshift: DISTSTYLE ALL, SORTKEY (date_day).
-- ----------------------------------------------------------------------------
DROP TABLE IF EXISTS marts.dim_date CASCADE;
CREATE TABLE marts.dim_date AS
SELECT
    d::date                          AS date_day,
    EXTRACT(YEAR FROM d)::int        AS year,
    EXTRACT(QUARTER FROM d)::int     AS quarter,
    EXTRACT(MONTH FROM d)::int       AS month,
    TRIM(TO_CHAR(d, 'Month'))        AS month_name,
    TO_CHAR(d, 'YYYY-MM')            AS year_month,
    EXTRACT(WEEK FROM d)::int        AS iso_week,
    EXTRACT(DOW FROM d)::int         AS day_of_week,        -- 0=Sunday .. 6=Saturday
    TRIM(TO_CHAR(d, 'Day'))          AS day_name,
    (EXTRACT(DOW FROM d) IN (0, 6))  AS is_weekend
FROM generate_series('2016-01-01'::date, '2018-12-31'::date, '1 day'::interval) d;

ALTER TABLE marts.dim_date ADD PRIMARY KEY (date_day);

-- ----------------------------------------------------------------------------
-- dim_customer: grain = customer_unique_id (the actual person - 96,096
-- distinct people placed 99,441 orders via 99,441 customer_id records, i.e.
-- some people ordered more than once). Location = most recent order's
-- address. first/last_order_date support cohort and recency analysis.
-- Redshift: DISTSTYLE ALL, SORTKEY (customer_unique_id).
-- ----------------------------------------------------------------------------
DROP TABLE IF EXISTS marts.dim_customer CASCADE;
CREATE TABLE marts.dim_customer AS
WITH customer_orders AS (
    SELECT
        c.customer_unique_id,
        c.customer_zip_code_prefix,
        c.customer_city,
        c.customer_state,
        o.order_purchase_timestamp,
        ROW_NUMBER() OVER (
            PARTITION BY c.customer_unique_id ORDER BY o.order_purchase_timestamp DESC
        ) AS rn_recent
    FROM staging.stg_customers c
    JOIN staging.stg_orders o ON o.customer_id = c.customer_id
),
agg AS (
    SELECT
        c.customer_unique_id,
        COUNT(*)                              AS n_lifetime_orders,
        MIN(o.order_purchase_timestamp)::date AS first_order_date,
        MAX(o.order_purchase_timestamp)::date AS last_order_date
    FROM staging.stg_customers c
    JOIN staging.stg_orders o ON o.customer_id = c.customer_id
    GROUP BY c.customer_unique_id
)
SELECT
    co.customer_unique_id,
    co.customer_zip_code_prefix,
    co.customer_city,
    co.customer_state,
    g.latitude  AS customer_latitude,
    g.longitude AS customer_longitude,
    a.n_lifetime_orders,
    a.first_order_date,
    a.last_order_date
FROM customer_orders co
JOIN agg a ON a.customer_unique_id = co.customer_unique_id
LEFT JOIN staging.stg_geolocation g ON g.zip_code_prefix = co.customer_zip_code_prefix
WHERE co.rn_recent = 1;

ALTER TABLE marts.dim_customer ADD PRIMARY KEY (customer_unique_id);

-- ----------------------------------------------------------------------------
-- dim_product
-- Redshift: DISTSTYLE ALL, SORTKEY (product_id).
-- ----------------------------------------------------------------------------
DROP TABLE IF EXISTS marts.dim_product CASCADE;
CREATE TABLE marts.dim_product AS
SELECT
    product_id,
    product_category_name,
    product_category_name_english,
    product_name_length,
    product_description_length,
    product_photos_qty,
    product_weight_g,
    product_length_cm,
    product_height_cm,
    product_width_cm,
    product_volume_cm3,
    dq_category_missing
FROM staging.stg_products;

ALTER TABLE marts.dim_product ADD PRIMARY KEY (product_id);

-- ----------------------------------------------------------------------------
-- dim_seller
-- Redshift: DISTSTYLE ALL, SORTKEY (seller_id).
-- ----------------------------------------------------------------------------
DROP TABLE IF EXISTS marts.dim_seller CASCADE;
CREATE TABLE marts.dim_seller AS
SELECT
    s.seller_id,
    s.seller_zip_code_prefix,
    s.seller_city,
    s.seller_state,
    g.latitude  AS seller_latitude,
    g.longitude AS seller_longitude
FROM staging.stg_sellers s
LEFT JOIN staging.stg_geolocation g ON g.zip_code_prefix = s.seller_zip_code_prefix;

ALTER TABLE marts.dim_seller ADD PRIMARY KEY (seller_id);

-- ----------------------------------------------------------------------------
-- dim_geography: zip-prefix grain, used for map visualizations / regional
-- joins independent of customer or seller.
-- Redshift: DISTSTYLE ALL, SORTKEY (zip_code_prefix).
-- ----------------------------------------------------------------------------
DROP TABLE IF EXISTS marts.dim_geography CASCADE;
CREATE TABLE marts.dim_geography AS
SELECT zip_code_prefix, city, state, latitude, longitude
FROM staging.stg_geolocation;

ALTER TABLE marts.dim_geography ADD PRIMARY KEY (zip_code_prefix);
