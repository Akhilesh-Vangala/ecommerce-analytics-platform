-- ============================================================================
-- RAW LAYER
-- One table per source CSV. Types loosely matched to source; minimal
-- constraints (PK only where source guarantees uniqueness). This layer
-- preserves source fidelity for lineage/debugging - cleaning happens in
-- the staging layer.
-- ============================================================================

CREATE SCHEMA IF NOT EXISTS raw;

DROP TABLE IF EXISTS raw.orders CASCADE;
CREATE TABLE raw.orders (
    order_id                        VARCHAR(32),
    customer_id                     VARCHAR(32),
    order_status                    VARCHAR(20),
    order_purchase_timestamp        TIMESTAMP,
    order_approved_at               TIMESTAMP,
    order_delivered_carrier_date    TIMESTAMP,
    order_delivered_customer_date   TIMESTAMP,
    order_estimated_delivery_date   TIMESTAMP
);

DROP TABLE IF EXISTS raw.order_items CASCADE;
CREATE TABLE raw.order_items (
    order_id            VARCHAR(32),
    order_item_id       INTEGER,
    product_id          VARCHAR(32),
    seller_id           VARCHAR(32),
    shipping_limit_date TIMESTAMP,
    price               NUMERIC(12,2),
    freight_value       NUMERIC(12,2)
);

DROP TABLE IF EXISTS raw.order_payments CASCADE;
CREATE TABLE raw.order_payments (
    order_id              VARCHAR(32),
    payment_sequential    INTEGER,
    payment_type          VARCHAR(20),
    payment_installments  INTEGER,
    payment_value         NUMERIC(12,2)
);

DROP TABLE IF EXISTS raw.order_reviews CASCADE;
CREATE TABLE raw.order_reviews (
    review_id                VARCHAR(32),
    order_id                 VARCHAR(32),
    review_score             INTEGER,
    review_comment_title     TEXT,
    review_comment_message   TEXT,
    review_creation_date     TIMESTAMP,
    review_answer_timestamp  TIMESTAMP
);

DROP TABLE IF EXISTS raw.customers CASCADE;
CREATE TABLE raw.customers (
    customer_id              VARCHAR(32),
    customer_unique_id       VARCHAR(32),
    customer_zip_code_prefix VARCHAR(5),
    customer_city            VARCHAR(100),
    customer_state           VARCHAR(2)
);

DROP TABLE IF EXISTS raw.products CASCADE;
CREATE TABLE raw.products (
    product_id                  VARCHAR(32),
    product_category_name       VARCHAR(100),
    product_name_lenght         INTEGER,
    product_description_lenght  INTEGER,
    product_photos_qty          INTEGER,
    product_weight_g            INTEGER,
    product_length_cm           INTEGER,
    product_height_cm           INTEGER,
    product_width_cm            INTEGER
);

DROP TABLE IF EXISTS raw.sellers CASCADE;
CREATE TABLE raw.sellers (
    seller_id              VARCHAR(32),
    seller_zip_code_prefix VARCHAR(5),
    seller_city            VARCHAR(100),
    seller_state           VARCHAR(2)
);

DROP TABLE IF EXISTS raw.geolocation CASCADE;
CREATE TABLE raw.geolocation (
    geolocation_zip_code_prefix VARCHAR(5),
    geolocation_lat             NUMERIC(15,10),
    geolocation_lng             NUMERIC(15,10),
    geolocation_city            VARCHAR(100),
    geolocation_state           VARCHAR(2)
);

DROP TABLE IF EXISTS raw.product_category_translation CASCADE;
CREATE TABLE raw.product_category_translation (
    product_category_name          VARCHAR(100),
    product_category_name_english   VARCHAR(100)
);
