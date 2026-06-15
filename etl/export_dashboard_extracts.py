"""Build all CSV extracts that feed the 7-page Tableau Public dashboard.

Each function below produces one (or a small family of) extract(s) for a single
dashboard page. All logic mirrors the validated analysis in notebooks/01-06, so the
dashboard numbers are guaranteed consistent with the notebook narrative -- this
script does not introduce any new analytical methodology, it re-packages
already-validated results into flat, pre-aggregated extracts that Tableau can
consume directly.

Usage:
    .venv/bin/python etl/export_dashboard_extracts.py

Output:
    dashboard/extracts/*.csv  (24 files, see EXTRACT CATALOG at bottom of file)
"""
from __future__ import annotations

import logging
from pathlib import Path

import numpy as np
import pandas as pd
from sklearn.cluster import KMeans
from sklearn.decomposition import PCA
from sklearn.ensemble import RandomForestClassifier
from sklearn.preprocessing import StandardScaler

from db import get_engine

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger("export_dashboard_extracts")

PROJECT_ROOT = Path(__file__).resolve().parent.parent
EXTRACTS_DIR = PROJECT_ROOT / "dashboard" / "extracts"

RANDOM_STATE = 42

# Brazilian state -> IBGE macro-region map (reused verbatim from NB3-NB6)
BR_REGION = {
    "AC": "North", "AP": "North", "AM": "North", "PA": "North", "RO": "North", "RR": "North", "TO": "North",
    "AL": "Northeast", "BA": "Northeast", "CE": "Northeast", "MA": "Northeast", "PB": "Northeast",
    "PE": "Northeast", "PI": "Northeast", "RN": "Northeast", "SE": "Northeast",
    "DF": "Central-West", "GO": "Central-West", "MT": "Central-West", "MS": "Central-West",
    "ES": "Southeast", "MG": "Southeast", "RJ": "Southeast", "SP": "Southeast",
    "PR": "South", "RS": "South", "SC": "South",
}
REGION_ORDER = ["North", "Northeast", "Central-West", "Southeast", "South"]

# 2-letter state code -> full Portuguese state name, for Tableau's built-in
# Brazil geocoding (State/Province geographic role) -- avoids needing an
# external shapefile/geojson for the choropleth maps on the Geography page.
BR_STATE_NAME = {
    "AC": "Acre", "AL": "Alagoas", "AP": "Amapá", "AM": "Amazonas", "BA": "Bahia",
    "CE": "Ceará", "DF": "Distrito Federal", "ES": "Espírito Santo", "GO": "Goiás",
    "MA": "Maranhão", "MT": "Mato Grosso", "MS": "Mato Grosso do Sul", "MG": "Minas Gerais",
    "PA": "Pará", "PB": "Paraíba", "PR": "Paraná", "PE": "Pernambuco", "PI": "Piauí",
    "RJ": "Rio de Janeiro", "RN": "Rio Grande do Norte", "RS": "Rio Grande do Sul",
    "RO": "Rondônia", "RR": "Roraima", "SC": "Santa Catarina", "SP": "São Paulo",
    "SE": "Sergipe", "TO": "Tocantins",
}


# ---------------------------------------------------------------------------
# Shared helpers
# ---------------------------------------------------------------------------
def haversine_km(lat1, lon1, lat2, lon2):
    """Great-circle distance in km (reused from NB3-NB6)."""
    R = 6371.0
    lat1, lon1, lat2, lon2 = map(np.radians, [lat1, lon1, lat2, lon2])
    dlat = lat2 - lat1
    dlon = lon2 - lon1
    a = np.sin(dlat / 2) ** 2 + np.cos(lat1) * np.cos(lat2) * np.sin(dlon / 2) ** 2
    return 2 * R * np.arcsin(np.sqrt(a))


def build_X(df, num_feats, cat_feats, ref_cols=None):
    """One-hot encode categoricals + concatenate numeric features (reused from NB6)."""
    X_num = df[num_feats].fillna(0)
    X_cat = pd.get_dummies(df[cat_feats].astype(str), drop_first=True)
    X = pd.concat([X_num, X_cat], axis=1)
    if ref_cols is not None:
        X = X.reindex(columns=ref_cols, fill_value=0)
    return X


def group_importance(importances: pd.Series, num_feats: list[str], cat_feats: list[str]) -> pd.DataFrame:
    """Collapse one-hot dummy importances back to their parent feature for a clean dashboard chart."""
    rows = []
    for feat in num_feats:
        if feat in importances.index:
            rows.append((feat, importances[feat]))
    for cat in cat_feats:
        total = sum(v for k, v in importances.items() if k.startswith(cat + "_"))
        rows.append((cat, total))
    s = pd.Series(dict(rows)).sort_values(ascending=False)
    out = s.reset_index()
    out.columns = ["feature", "importance"]
    out["rank"] = range(1, len(out) + 1)
    out["pct_of_total_importance"] = 100 * out["importance"] / out["importance"].sum()
    return out


def risk_tier(decile: int) -> str:
    if decile <= 2:
        return "High Risk (top 20%)"
    if decile <= 5:
        return "Medium Risk (next 30%)"
    return "Low Risk (bottom 50%)"


def add_state_name(df: pd.DataFrame, state_col: str, new_col: str = "state_name") -> pd.DataFrame:
    """Insert a full-Portuguese-name column next to `state_col` for Tableau geocoding."""
    idx = df.columns.get_loc(state_col) + 1
    df.insert(idx, new_col, df[state_col].map(BR_STATE_NAME))
    return df


def write_csv(df: pd.DataFrame, name: str) -> None:
    path = EXTRACTS_DIR / name
    df.to_csv(path, index=False)
    log.info("wrote %-38s %8s rows x %2d cols", name, f"{len(df):,}", df.shape[1])


# ---------------------------------------------------------------------------
# Base pulls (shared across multiple extracts)
# ---------------------------------------------------------------------------
def load_orders(engine) -> pd.DataFrame:
    orders = pd.read_sql("""
        SELECT
            fo.order_id, fo.customer_unique_id, fo.customer_state, dc.customer_city,
            dc.customer_latitude, dc.customer_longitude,
            fo.order_status, fo.order_purchase_date,
            fo.n_items, fo.n_distinct_sellers, fo.n_distinct_products,
            fo.order_total_value, fo.items_price_total, fo.freight_value_total,
            fo.primary_payment_type, fo.max_installments,
            fo.estimated_delivery_days, fo.actual_delivery_days, fo.delivery_delay_days,
            fo.is_late, fo.is_delivered, fo.is_canceled, fo.dq_delivered_missing_date,
            fo.review_score, fo.has_review,
            dp.product_category_name_english AS category,
            ds.seller_id, ds.seller_state, ds.seller_latitude, ds.seller_longitude
        FROM marts.fact_orders fo
        JOIN marts.dim_customer dc ON dc.customer_unique_id = fo.customer_unique_id
        LEFT JOIN marts.fact_order_items foi ON foi.order_id = fo.order_id AND foi.order_item_id = 1
        LEFT JOIN marts.dim_product dp ON dp.product_id = foi.product_id
        LEFT JOIN marts.dim_seller ds ON ds.seller_id = foi.seller_id
        ORDER BY fo.order_id
    """, engine)

    orders["order_purchase_date"] = pd.to_datetime(orders["order_purchase_date"])
    orders["customer_region"] = orders["customer_state"].map(BR_REGION)
    orders["seller_region"] = orders["seller_state"].map(BR_REGION)
    orders["is_cross_region"] = np.where(
        orders["seller_region"].notna(),
        (orders["customer_region"] != orders["seller_region"]).astype("Int64"),
        pd.NA,
    )
    orders["distance_km"] = haversine_km(
        orders["customer_latitude"], orders["customer_longitude"],
        orders["seller_latitude"], orders["seller_longitude"],
    )
    orders["freight_ratio"] = np.where(
        orders["order_total_value"] > 0,
        orders["freight_value_total"] / orders["order_total_value"],
        np.nan,
    )
    orders["purchase_year"] = orders["order_purchase_date"].dt.year
    orders["purchase_month"] = orders["order_purchase_date"].dt.month
    orders["purchase_dow"] = orders["order_purchase_date"].dt.dayofweek
    orders["is_negative_review"] = np.where(
        orders["review_score"].notna(), (orders["review_score"] <= 2).astype("Int64"), pd.NA
    )
    orders["category"] = orders["category"].fillna("unknown")

    top_cats = orders["category"].value_counts()
    top_cats = top_cats[(top_cats >= 500) & (top_cats.index != "unknown")].index.tolist()
    orders["category_grp"] = np.where(
        orders["category"].isin(top_cats), orders["category"],
        np.where(orders["category"] == "unknown", "unknown", "other"),
    )
    return orders


def load_items(engine) -> pd.DataFrame:
    items = pd.read_sql("""
        SELECT
            foi.order_id, foi.order_item_id, foi.product_id,
            dp.product_category_name_english AS category,
            foi.seller_id, ds.seller_state,
            fo.customer_state, fo.order_purchase_date, fo.order_status,
            foi.price, foi.freight_value, foi.item_total_value
        FROM marts.fact_order_items foi
        JOIN marts.dim_product dp ON dp.product_id = foi.product_id
        JOIN marts.dim_seller ds ON ds.seller_id = foi.seller_id
        JOIN marts.fact_orders fo ON fo.order_id = foi.order_id
        ORDER BY foi.order_id, foi.order_item_id
    """, engine)
    items["order_purchase_date"] = pd.to_datetime(items["order_purchase_date"])
    items["category"] = items["category"].fillna("unknown")
    items["customer_region"] = items["customer_state"].map(BR_REGION)
    items["seller_region"] = items["seller_state"].map(BR_REGION)

    top_cats = items["category"].value_counts()
    top_cats = top_cats[(top_cats >= 500) & (top_cats.index != "unknown")].index.tolist()
    items["category_grp"] = np.where(
        items["category"].isin(top_cats), items["category"],
        np.where(items["category"] == "unknown", "unknown", "other"),
    )
    return items


# ---------------------------------------------------------------------------
# PAGE 1 -- Executive Overview
# ---------------------------------------------------------------------------
def build_page1_executive(orders: pd.DataFrame) -> None:
    valid = orders[~orders["order_status"].isin(["canceled", "unavailable"])].copy()

    monthly = valid.groupby(valid["order_purchase_date"].dt.to_period("M")).agg(
        n_orders=("order_id", "count"),
        gmv=("order_total_value", "sum"),
    ).reset_index()
    monthly["month"] = monthly["order_purchase_date"].dt.to_timestamp()
    monthly = monthly.drop(columns=["order_purchase_date"]).sort_values("month")

    delivered = valid[valid["is_delivered"] & valid["delivery_delay_days"].notna()]
    monthly_otd = delivered.groupby(delivered["order_purchase_date"].dt.to_period("M")).agg(
        n_delivered=("order_id", "count"),
        n_late=("is_late", "sum"),
        avg_actual_delivery_days=("actual_delivery_days", "mean"),
        avg_delay_days=("delivery_delay_days", "mean"),
    ).reset_index()
    monthly_otd["month"] = monthly_otd["order_purchase_date"].dt.to_timestamp()
    monthly_otd = monthly_otd.drop(columns=["order_purchase_date"])

    reviewed = valid.dropna(subset=["review_score"])
    monthly_review = reviewed.groupby(reviewed["order_purchase_date"].dt.to_period("M")).agg(
        avg_review_score=("review_score", "mean"),
    ).reset_index()
    monthly_review["month"] = monthly_review["order_purchase_date"].dt.to_timestamp()
    monthly_review = monthly_review.drop(columns=["order_purchase_date"])

    # new vs returning (full-history order_seq)
    valid_sorted = valid.sort_values(["customer_unique_id", "order_purchase_date", "order_id"])
    valid_sorted["order_seq"] = valid_sorted.groupby("customer_unique_id").cumcount() + 1
    monthly_repeat = valid_sorted.groupby(valid_sorted["order_purchase_date"].dt.to_period("M")).agg(
        new_customer_orders=("order_seq", lambda s: (s == 1).sum()),
        returning_customer_orders=("order_seq", lambda s: (s > 1).sum()),
    ).reset_index()
    monthly_repeat["month"] = monthly_repeat["order_purchase_date"].dt.to_timestamp()
    monthly_repeat = monthly_repeat.drop(columns=["order_purchase_date"])

    monthly_kpis = (
        monthly.merge(monthly_otd, on="month", how="left")
               .merge(monthly_review, on="month", how="left")
               .merge(monthly_repeat, on="month", how="left")
               .sort_values("month")
               .reset_index(drop=True)
    )
    monthly_kpis["aov"] = monthly_kpis["gmv"] / monthly_kpis["n_orders"]
    monthly_kpis["pct_late"] = 100 * monthly_kpis["n_late"] / monthly_kpis["n_delivered"]
    monthly_kpis["pct_orders_from_returning"] = 100 * monthly_kpis["returning_customer_orders"] / monthly_kpis["n_orders"]
    monthly_kpis["gmv_mom_pct"] = 100 * monthly_kpis["gmv"].pct_change()
    monthly_kpis["gmv_3mo_moving_avg"] = monthly_kpis["gmv"].rolling(3).mean()
    monthly_kpis["cumulative_gmv"] = monthly_kpis["gmv"].cumsum()
    # Sep-2016/Oct-2018 are partial ramp-up/cutoff months; Jan-2017 to Aug-2018 are full months
    monthly_kpis["is_full_month"] = monthly_kpis["month"].between("2017-01-01", "2018-08-01")
    write_csv(monthly_kpis, "monthly_kpis.csv")

    # Seasonality: trailing-3mo-avg de-trending over the full-month window (Q1.7 logic)
    season = monthly_kpis[monthly_kpis["is_full_month"]][["month", "gmv", "n_orders"]].copy().reset_index(drop=True)
    season["trailing_3mo_avg_gmv"] = season["gmv"].shift(1).rolling(3).mean()
    season["pct_above_trailing_avg"] = 100 * (season["gmv"] - season["trailing_3mo_avg_gmv"]) / season["trailing_3mo_avg_gmv"]
    season["is_seasonal_spike"] = season["gmv"] > 1.3 * season["trailing_3mo_avg_gmv"]
    season = season.dropna(subset=["trailing_3mo_avg_gmv"]).reset_index(drop=True)
    write_csv(season, "seasonality_analysis.csv")

    # KPI summary (1 row of headline metrics for BAN tiles)
    n_total_orders = len(orders)
    n_valid_orders = len(valid)
    n_customers = orders["customer_unique_id"].nunique()
    n_repeat_customers = int((valid_sorted.groupby("customer_unique_id")["order_seq"].max() > 1).sum())
    total_gmv = valid["order_total_value"].sum()
    aov = total_gmv / n_valid_orders
    pct_late_overall = 100 * delivered["is_late"].mean()
    avg_review_overall = valid["review_score"].mean()
    pct_negative_overall = 100 * (valid["review_score"] <= 2).mean()
    n_sellers = orders["seller_id"].nunique()

    kpi_summary = pd.DataFrame([{
        "total_orders": n_total_orders,
        "valid_orders": n_valid_orders,
        "total_customers": n_customers,
        "repeat_customers": n_repeat_customers,
        "repeat_rate_pct": round(100 * n_repeat_customers / n_customers, 2),
        "total_gmv": round(total_gmv, 2),
        "aov": round(aov, 2),
        "pct_late_overall": round(pct_late_overall, 2),
        "avg_review_score_overall": round(avg_review_overall, 3),
        "pct_negative_review_overall": round(pct_negative_overall, 2),
        "total_sellers": n_sellers,
        "date_range_start": str(valid["order_purchase_date"].min().date()),
        "date_range_end": str(valid["order_purchase_date"].max().date()),
    }])
    write_csv(kpi_summary, "kpi_summary.csv")


# ---------------------------------------------------------------------------
# PAGE 2 -- Sales & Category Performance
# ---------------------------------------------------------------------------
def build_page2_category(orders: pd.DataFrame, items: pd.DataFrame) -> None:
    valid = orders[~orders["order_status"].isin(["canceled", "unavailable"])].copy()
    delivered = valid[valid["is_delivered"] & ~valid["dq_delivered_missing_date"]].copy()
    items_valid = items[~items["order_status"].isin(["canceled", "unavailable"])].copy()

    # Category summary: revenue/units (item grain) + quality (order grain, item-1 category)
    cat_rev = items_valid.groupby("category").agg(
        n_items_sold=("order_id", "count"),
        n_orders_containing=("order_id", "nunique"),
        revenue=("price", "sum"),
    ).reset_index().sort_values("revenue", ascending=False)
    cat_rev["pct_of_total_revenue"] = 100 * cat_rev["revenue"] / cat_rev["revenue"].sum()
    cat_rev["cumulative_pct_of_revenue"] = cat_rev["pct_of_total_revenue"].cumsum()
    cat_rev["revenue_rank"] = range(1, len(cat_rev) + 1)

    cat_quality = delivered.dropna(subset=["review_score"]).groupby("category").agg(
        n_primary_orders=("order_id", "count"),
        avg_review_score=("review_score", "mean"),
    ).reset_index()
    cat_late = delivered.groupby("category").agg(pct_late=("is_late", "mean")).reset_index()
    cat_quality = cat_quality.merge(cat_late, on="category", how="left")

    category_summary = cat_rev.merge(cat_quality, on="category", how="left")
    category_summary["pct_late"] = 100 * category_summary["pct_late"].astype(float)
    write_csv(category_summary, "category_summary.csv")

    # Category monthly mix: top-10 categories by revenue + 'other', full-month window
    top10 = cat_rev.head(10)["category"].tolist()
    mix = items_valid[items_valid["order_purchase_date"].between("2017-01-01", "2018-08-31")].copy()
    mix["category_mix"] = np.where(mix["category"].isin(top10), mix["category"], "other")
    cat_monthly = mix.groupby([mix["order_purchase_date"].dt.to_period("M"), "category_mix"]).agg(
        revenue=("price", "sum"),
        n_items_sold=("order_id", "count"),
    ).reset_index()
    cat_monthly["month"] = cat_monthly["order_purchase_date"].dt.to_timestamp()
    cat_monthly = cat_monthly.drop(columns=["order_purchase_date"])
    cat_monthly["month_total"] = cat_monthly.groupby("month")["revenue"].transform("sum")
    cat_monthly["share_of_month"] = 100 * cat_monthly["revenue"] / cat_monthly["month_total"]
    write_csv(cat_monthly, "category_monthly_mix.csv")

    # Top 50 products by revenue
    top_products = items_valid.groupby(["product_id", "category"]).agg(
        n_sold=("order_id", "count"),
        revenue=("price", "sum"),
        avg_price=("price", "mean"),
    ).reset_index().sort_values("revenue", ascending=False).head(50).reset_index(drop=True)
    top_products["revenue_rank"] = range(1, len(top_products) + 1)
    write_csv(top_products, "top_products.csv")


# ---------------------------------------------------------------------------
# PAGE 3 -- Geography
# ---------------------------------------------------------------------------
def build_page3_geography(orders: pd.DataFrame, items: pd.DataFrame) -> None:
    valid = orders[~orders["order_status"].isin(["canceled", "unavailable"])].copy()
    delivered = valid[valid["is_delivered"] & ~valid["dq_delivered_missing_date"]].copy()
    items_valid = items[~items["order_status"].isin(["canceled", "unavailable"])].copy()

    # Customer-state demand summary
    geo_cust = valid.groupby("customer_state").agg(
        n_customers=("customer_unique_id", "nunique"),
        n_orders=("order_id", "count"),
        gmv=("order_total_value", "sum"),
    ).reset_index()
    geo_cust["region"] = geo_cust["customer_state"].map(BR_REGION)
    geo_cust["aov"] = geo_cust["gmv"] / geo_cust["n_orders"]
    geo_cust["pct_of_total_gmv"] = 100 * geo_cust["gmv"] / geo_cust["gmv"].sum()
    geo_cust = geo_cust.sort_values("gmv", ascending=False).reset_index(drop=True)
    geo_cust["cumulative_pct_gmv"] = geo_cust["pct_of_total_gmv"].cumsum()
    geo_cust["gmv_rank"] = range(1, len(geo_cust) + 1)

    geo_otd = delivered.groupby("customer_state").agg(
        n_delivered=("order_id", "count"),
        pct_late=("is_late", "mean"),
        avg_actual_delivery_days=("actual_delivery_days", "mean"),
        avg_delay_days=("delivery_delay_days", "mean"),
        avg_distance_km=("distance_km", "mean"),
    ).reset_index()
    geo_otd["pct_late"] = 100 * geo_otd["pct_late"].astype(float)
    geo_review = delivered.dropna(subset=["review_score"]).groupby("customer_state").agg(
        avg_review_score=("review_score", "mean")
    ).reset_index()

    geo_state_summary = geo_cust.merge(geo_otd, on="customer_state", how="left").merge(geo_review, on="customer_state", how="left")
    geo_state_summary = add_state_name(geo_state_summary, "customer_state")
    write_csv(geo_state_summary, "geo_customer_state_summary.csv")

    # Seller-state supply summary
    geo_seller = items_valid.groupby("seller_state").agg(
        n_sellers=("seller_id", "nunique"),
        n_items=("order_id", "count"),
        revenue=("price", "sum"),
    ).reset_index()
    geo_seller["region"] = geo_seller["seller_state"].map(BR_REGION)
    geo_seller["pct_of_total_revenue"] = 100 * geo_seller["revenue"] / geo_seller["revenue"].sum()
    geo_seller = geo_seller.sort_values("revenue", ascending=False).reset_index(drop=True)
    geo_seller["cumulative_pct"] = geo_seller["pct_of_total_revenue"].cumsum()
    geo_seller["revenue_rank"] = range(1, len(geo_seller) + 1)
    geo_seller = add_state_name(geo_seller, "seller_state")
    write_csv(geo_seller, "geo_seller_state_summary.csv")

    # Region x region flow matrix (demand vs supply geography, NB3 H6)
    flow_base = delivered.dropna(subset=["seller_region"]).copy()
    region_flow = flow_base.groupby(["customer_region", "seller_region"]).agg(
        n_orders=("order_id", "count"),
        pct_late=("is_late", "mean"),
        avg_distance_km=("distance_km", "mean"),
        avg_freight_ratio=("freight_ratio", "mean"),
    ).reset_index()
    region_flow["pct_late"] = 100 * region_flow["pct_late"].astype(float)
    region_flow["is_cross_region"] = region_flow["customer_region"] != region_flow["seller_region"]
    write_csv(region_flow, "region_flow_matrix.csv")


# ---------------------------------------------------------------------------
# PAGE 4 -- Delivery & Fulfillment Operations
# ---------------------------------------------------------------------------
def build_page4_fulfillment(engine, orders: pd.DataFrame) -> None:
    valid = orders[~orders["order_status"].isin(["canceled", "unavailable"])].copy()
    delivered = valid[valid["is_delivered"] & ~valid["dq_delivered_missing_date"]].copy()

    # Cycle-time stage breakdown (Q3.3, run directly against the DB for exact percentiles)
    cycle_time_stages = pd.read_sql("""
    SELECT 'approval_hours (purchase -> approved)' AS stage,
           COUNT(*) AS n,
           ROUND(AVG(approval_hours)::numeric, 2) AS avg_value,
           ROUND(PERCENTILE_CONT(0.5) WITHIN GROUP (ORDER BY approval_hours)::numeric, 2) AS median_value,
           ROUND(PERCENTILE_CONT(0.9) WITHIN GROUP (ORDER BY approval_hours)::numeric, 2) AS p90_value,
           'hours' AS unit, 1 AS stage_order
    FROM marts.fact_orders
    WHERE order_approved_at IS NOT NULL
    UNION ALL
    SELECT 'carrier_handoff_days (approved -> carrier)',
           COUNT(*),
           ROUND(AVG(carrier_handoff_days)::numeric, 2),
           ROUND(PERCENTILE_CONT(0.5) WITHIN GROUP (ORDER BY carrier_handoff_days)::numeric, 2),
           ROUND(PERCENTILE_CONT(0.9) WITHIN GROUP (ORDER BY carrier_handoff_days)::numeric, 2),
           'days', 2
    FROM marts.fact_orders
    WHERE order_delivered_carrier_date IS NOT NULL AND NOT dq_carrier_before_approval
    UNION ALL
    SELECT 'shipping_transit_days (carrier -> customer)',
           COUNT(*),
           ROUND(AVG(shipping_transit_days)::numeric, 2),
           ROUND(PERCENTILE_CONT(0.5) WITHIN GROUP (ORDER BY shipping_transit_days)::numeric, 2),
           ROUND(PERCENTILE_CONT(0.9) WITHIN GROUP (ORDER BY shipping_transit_days)::numeric, 2),
           'days', 3
    FROM marts.fact_orders
    WHERE order_delivered_customer_date IS NOT NULL AND order_delivered_carrier_date IS NOT NULL
      AND NOT dq_delivered_before_carrier
    UNION ALL
    SELECT 'actual_delivery_days (purchase -> customer, end-to-end)',
           COUNT(*),
           ROUND(AVG(actual_delivery_days)::numeric, 2),
           ROUND(PERCENTILE_CONT(0.5) WITHIN GROUP (ORDER BY actual_delivery_days)::numeric, 2),
           ROUND(PERCENTILE_CONT(0.9) WITHIN GROUP (ORDER BY actual_delivery_days)::numeric, 2),
           'days', 4
    FROM marts.fact_orders
    WHERE is_delivered AND NOT dq_delivered_missing_date
    ORDER BY stage_order
    """, engine)
    write_csv(cycle_time_stages, "cycle_time_stages.csv")

    # Delay bucket vs review score (Q3.5)
    db = delivered.dropna(subset=["review_score"]).copy()
    db["delay_bucket"] = pd.cut(
        db["delivery_delay_days"],
        bins=[-np.inf, -2, 0, 3, 7, np.inf],
        labels=["1. Early (2+ days ahead)", "2. On-time (0-1 day ahead)", "3. Late 1-3 days", "4. Late 4-7 days", "5. Late 8+ days"],
    )
    delay_bucket_review = db.groupby("delay_bucket", observed=True).agg(
        n_orders=("order_id", "count"),
        avg_review_score=("review_score", "mean"),
        pct_1star=("review_score", lambda s: 100 * (s == 1).mean()),
        pct_5star=("review_score", lambda s: 100 * (s == 5).mean()),
    ).reset_index()
    write_csv(delay_bucket_review, "delay_bucket_vs_review.csv")

    # Feb-Mar 2018 anomaly drill-down (Q3.7/Q3.8, Carnival hypothesis)
    anomaly = delivered[delivered["order_purchase_date"].between("2018-01-15", "2018-04-15")].copy()
    fulfillment_weekly = anomaly.groupby(anomaly["order_purchase_date"].dt.to_period("W").dt.start_time).agg(
        n_delivered=("order_id", "count"),
        n_late=("is_late", "sum"),
        avg_actual_delivery_days=("actual_delivery_days", "mean"),
    ).reset_index().rename(columns={"order_purchase_date": "week"})
    fulfillment_weekly["pct_late"] = 100 * fulfillment_weekly["n_late"] / fulfillment_weekly["n_delivered"]
    write_csv(fulfillment_weekly, "fulfillment_weekly_2018.csv")

    # State-level comparison: normal period vs spike period
    normal = delivered[delivered["order_purchase_date"].between("2017-09-01", "2017-12-31")]
    spike = delivered[delivered["order_purchase_date"].between("2018-02-01", "2018-03-31")]
    normal_state = normal.groupby("customer_state").agg(n_delivered=("order_id", "count"), pct_late=("is_late", "mean")).reset_index()
    spike_state = spike.groupby("customer_state").agg(n_delivered=("order_id", "count"), pct_late=("is_late", "mean")).reset_index()
    normal_state["period"] = "Normal (Sep-Dec 2017)"
    spike_state["period"] = "Spike (Feb-Mar 2018)"
    anomaly_state = pd.concat([normal_state, spike_state], ignore_index=True)
    anomaly_state["pct_late"] = 100 * anomaly_state["pct_late"].astype(float)
    anomaly_state = anomaly_state[anomaly_state["n_delivered"] >= 20].reset_index(drop=True)
    write_csv(anomaly_state, "anomaly_state_comparison.csv")


# ---------------------------------------------------------------------------
# PAGE 5 -- Customer Segmentation (RFM + K-Means + PCA)
# ---------------------------------------------------------------------------
def build_page5_segmentation(engine) -> None:
    orders = pd.read_sql("""
        SELECT
            customer_unique_id, order_id, order_status, order_purchase_date,
            order_total_value, freight_value_total, review_score,
            delivery_delay_days, is_late, is_delivered, max_installments,
            n_items, customer_state
        FROM marts.fact_orders
        ORDER BY order_id
    """, engine)
    orders["order_purchase_date"] = pd.to_datetime(orders["order_purchase_date"])

    items = pd.read_sql("""
        SELECT oi.order_id, dp.product_category_name_english AS category
        FROM marts.fact_order_items oi
        JOIN marts.dim_product dp ON dp.product_id = oi.product_id
        WHERE dp.product_category_name_english IS NOT NULL
        ORDER BY oi.order_id
    """, engine)

    valid = orders[~orders["order_status"].isin(["canceled", "unavailable"])].copy()

    order_cust = valid[["order_id", "customer_unique_id"]]
    n_categories = (
        items.merge(order_cust, on="order_id", how="inner")
        .groupby("customer_unique_id")["category"].nunique()
        .rename("n_categories")
    )

    snapshot_date = valid["order_purchase_date"].max() + pd.Timedelta(days=1)

    rfm = valid.groupby("customer_unique_id").agg(
        frequency=("order_id", "count"),
        monetary=("order_total_value", "sum"),
        last_order_date=("order_purchase_date", "max"),
        customer_state=("customer_state", "first"),
    ).reset_index()
    rfm["recency_days"] = (snapshot_date - rfm["last_order_date"]).dt.days
    rfm["avg_order_value"] = rfm["monetary"] / rfm["frequency"]

    avg_review = (
        valid.dropna(subset=["review_score"])
        .groupby("customer_unique_id")["review_score"].mean()
        .rename("avg_review_score")
    )
    delivered = valid[valid["is_delivered"] & valid["delivery_delay_days"].notna() & valid["is_late"].notna()]
    delay_agg = delivered.groupby("customer_unique_id").agg(
        avg_delivery_delay_days=("delivery_delay_days", "mean"),
        pct_late=("is_late", "mean"),
    ).reset_index()
    # Scale to 0-100 (percentage points) to match every other pct_* field across the
    # extract catalog (geo_*, category_summary, rfm_segment_summary, etc.) -- keeps the
    # Tableau number-format convention ("0.0\%" custom format) uniform across all 24 files.
    delay_agg["pct_late"] = 100 * delay_agg["pct_late"].astype(float)

    valid["freight_ratio"] = np.where(
        valid["order_total_value"] > 0,
        valid["freight_value_total"] / valid["order_total_value"],
        np.nan,
    )
    freight_agg = valid.groupby("customer_unique_id")["freight_ratio"].mean().rename("avg_freight_ratio")
    inst_agg = valid.groupby("customer_unique_id")["max_installments"].mean().rename("avg_installments")

    cust = (
        rfm.merge(avg_review, on="customer_unique_id", how="left")
           .merge(delay_agg, on="customer_unique_id", how="left")
           .merge(freight_agg, on="customer_unique_id", how="left")
           .merge(inst_agg, on="customer_unique_id", how="left")
           .merge(n_categories, on="customer_unique_id", how="left")
    )
    cust["n_categories"] = cust["n_categories"].fillna(0).astype(int)

    cust_clean = cust.dropna(
        subset=["avg_review_score", "avg_delivery_delay_days", "avg_freight_ratio", "avg_installments"]
    ).copy()
    cust_clean["region"] = cust_clean["customer_state"].map(BR_REGION)
    cust_clean["is_repeat"] = (cust_clean["frequency"] > 1).astype(int)
    cust_clean["log_monetary"] = np.log1p(cust_clean["monetary"])
    cust_clean["log_recency"] = np.log1p(cust_clean["recency_days"])
    cust_clean["log_avg_order_value"] = np.log1p(cust_clean["avg_order_value"])

    # RFM quintiles + named segments (Q2.1 / NB5 logic)
    cust_clean["r_score"] = pd.qcut(cust_clean["recency_days"].rank(method="first"), 5, labels=[5, 4, 3, 2, 1]).astype(int)
    cust_clean["m_score"] = pd.qcut(cust_clean["monetary"].rank(method="first"), 5, labels=[1, 2, 3, 4, 5]).astype(int)

    def rfm_segment(row):
        r, m = row["r_score"], row["m_score"]
        if r >= 4 and m >= 4:
            return "Champions (recent + high spend)"
        if r <= 2 and m >= 4:
            return "High-Value Lapsed (win-back priority)"
        if r >= 4 and m <= 2:
            return "New/Recent Low-Spend"
        if r <= 2 and m <= 2:
            return "Low-Value Lapsed"
        return "Mid-Value"

    cust_clean["rfm_segment"] = cust_clean.apply(rfm_segment, axis=1)

    rfm_segment_summary = cust_clean.groupby("rfm_segment").agg(
        n_customers=("customer_unique_id", "count"),
        avg_monetary=("monetary", "mean"),
        avg_recency_days=("recency_days", "mean"),
        total_revenue=("monetary", "sum"),
        pct_repeat=("is_repeat", "mean"),
    ).reset_index()
    rfm_segment_summary["pct_customers"] = 100 * rfm_segment_summary["n_customers"] / rfm_segment_summary["n_customers"].sum()
    rfm_segment_summary["pct_revenue"] = 100 * rfm_segment_summary["total_revenue"] / rfm_segment_summary["total_revenue"].sum()
    rfm_segment_summary["pct_repeat"] = 100 * rfm_segment_summary["pct_repeat"]
    rfm_segment_summary = rfm_segment_summary.sort_values("pct_revenue", ascending=False).reset_index(drop=True)
    write_csv(rfm_segment_summary, "rfm_segment_summary.csv")

    # K-Means (4 clusters, NB5 feature set)
    feature_cols = [
        "log_recency", "log_monetary", "log_avg_order_value", "frequency",
        "avg_review_score", "avg_delivery_delay_days", "pct_late",
        "avg_freight_ratio", "avg_installments", "n_categories",
    ]
    scaler = StandardScaler()
    X_scaled = scaler.fit_transform(cust_clean[feature_cols].values)

    kmeans = KMeans(n_clusters=4, random_state=RANDOM_STATE, n_init=10)
    cust_clean["cluster"] = kmeans.fit_predict(X_scaled)

    profile_cols = ["recency_days", "frequency", "monetary", "avg_order_value",
                    "avg_review_score", "avg_delivery_delay_days", "pct_late",
                    "avg_freight_ratio", "avg_installments", "n_categories"]
    profile = cust_clean.groupby("cluster")[profile_cols].mean()
    sizes = cust_clean["cluster"].value_counts().sort_index()
    profile.insert(0, "n_customers", sizes)
    profile["pct_customers"] = 100 * sizes / sizes.sum()
    profile["pct_revenue"] = 100 * cust_clean.groupby("cluster")["monetary"].sum() / cust_clean["monetary"].sum()
    profile["pct_repeat"] = 100 * cust_clean.groupby("cluster")["is_repeat"].mean()

    # Dynamic, characteristic-based label assignment -- sklearn cluster ids are arbitrary
    # across reruns, so map by the trait that defines each named segment, not by index:
    #   1) Loyal Repeat Customers: pct_repeat is far higher in one cluster (~70%) than the
    #      ~1-2% baseline everywhere else -- pick this first, it's the most extreme signal.
    #   2) At-Risk: Late & Unhappy: highest avg delivery delay (most positive = late) among
    #      what remains.
    #   3) Core High-Value: among what's left, the cluster contributing the largest SHARE OF
    #      TOTAL REVENUE (pct_revenue) -- not necessarily the highest per-customer monetary,
    #      since a small niche cluster can have a higher average ticket but matter far less
    #      to total GMV.
    #   4) Budget Satisfied: whatever remains.
    remaining = set(profile.index)
    loyal = profile.loc[list(remaining), "pct_repeat"].idxmax()
    remaining.discard(loyal)
    at_risk = profile.loc[list(remaining), "avg_delivery_delay_days"].idxmax()
    remaining.discard(at_risk)
    core_hv = profile.loc[list(remaining), "pct_revenue"].idxmax()
    remaining.discard(core_hv)
    budget = list(remaining)[0]

    segment_names = {
        core_hv: "Core High-Value",
        loyal: "Loyal Repeat Customers",
        at_risk: "At-Risk: Late & Unhappy",
        budget: "Budget Satisfied",
    }
    cust_clean["segment"] = cust_clean["cluster"].map(segment_names)

    named_profile = profile.rename(index=segment_names).reset_index().rename(columns={"cluster": "segment"})
    write_csv(named_profile, "segment_profile_summary.csv")

    # PCA (2D projection for the customer-segment scatter)
    pca = PCA(n_components=2, random_state=RANDOM_STATE)
    pcs = pca.fit_transform(X_scaled)
    cust_clean["pc1"] = pcs[:, 0]
    cust_clean["pc2"] = pcs[:, 1]

    cust_clean = add_state_name(cust_clean, "customer_state")
    customer_segments = cust_clean[[
        "customer_unique_id", "customer_state", "state_name", "region", "last_order_date",
        "recency_days", "frequency", "monetary", "avg_order_value",
        "avg_review_score", "avg_delivery_delay_days", "pct_late",
        "avg_freight_ratio", "avg_installments", "n_categories", "is_repeat",
        "r_score", "m_score", "rfm_segment", "cluster", "segment", "pc1", "pc2",
    ]].copy()
    write_csv(customer_segments, "customer_segments.csv")


# ---------------------------------------------------------------------------
# PAGE 6 -- Seller Marketplace
# ---------------------------------------------------------------------------
def build_page6_sellers(orders: pd.DataFrame, items: pd.DataFrame) -> None:
    valid = orders[~orders["order_status"].isin(["canceled", "unavailable"])].copy()
    items_valid = items[~items["order_status"].isin(["canceled", "unavailable"])].copy()

    item_order_quality = items_valid.merge(
        valid[["order_id", "review_score", "is_delivered", "is_late", "dq_delivered_missing_date"]],
        on="order_id", how="left",
    )
    seller_agg = item_order_quality.groupby("seller_id").agg(
        seller_state=("seller_state", "first"),
        n_orders=("order_id", "nunique"),
        n_items=("order_id", "count"),
        revenue=("price", "sum"),
        avg_review_score=("review_score", "mean"),
    ).reset_index()
    seller_late = item_order_quality[
        item_order_quality["is_delivered"] & ~item_order_quality["dq_delivered_missing_date"].fillna(False)
    ].groupby("seller_id").agg(
        n_delivered=("order_id", "nunique"), pct_late=("is_late", "mean"),
    ).reset_index()
    seller_agg = seller_agg.merge(seller_late, on="seller_id", how="left")
    seller_agg["region"] = seller_agg["seller_state"].map(BR_REGION)
    seller_agg["pct_late"] = 100 * seller_agg["pct_late"].astype(float)
    seller_agg["avg_revenue_per_order"] = seller_agg["revenue"] / seller_agg["n_orders"]
    seller_agg["revenue_decile"] = pd.qcut(seller_agg["revenue"].rank(method="first"), 10, labels=False)
    seller_agg["revenue_decile"] = 10 - seller_agg["revenue_decile"]  # 1 = highest revenue
    seller_scorecard = seller_agg.sort_values("revenue", ascending=False).reset_index(drop=True)
    seller_scorecard["revenue_rank"] = range(1, len(seller_scorecard) + 1)
    seller_scorecard = add_state_name(seller_scorecard, "seller_state")
    write_csv(seller_scorecard, "seller_scorecard.csv")

    seller_pareto = seller_agg.groupby("revenue_decile").agg(
        n_sellers=("seller_id", "count"),
        total_orders=("n_orders", "sum"),
        decile_revenue=("revenue", "sum"),
    ).reset_index().sort_values("revenue_decile")
    seller_pareto["pct_of_total_revenue"] = 100 * seller_pareto["decile_revenue"] / seller_pareto["decile_revenue"].sum()
    seller_pareto["cumulative_pct_of_revenue"] = seller_pareto["pct_of_total_revenue"].cumsum()
    write_csv(seller_pareto, "seller_pareto_deciles.csv")


# ---------------------------------------------------------------------------
# PAGE 7 -- Predictive Risk Scoring (Model A: late delivery, Model B: negative review)
# ---------------------------------------------------------------------------
def build_page7_risk_scores(engine) -> None:
    # ----- Model A: late-delivery risk (order-time features only) -----
    dfA = pd.read_sql("""
        SELECT
            fo.order_id, fo.order_purchase_date, fo.order_total_value,
            fo.freight_value_total, fo.n_items, fo.primary_payment_type,
            fo.max_installments, fo.estimated_delivery_days, fo.is_late,
            fo.customer_state, ds.seller_state,
            dc.customer_latitude, dc.customer_longitude,
            ds.seller_latitude, ds.seller_longitude,
            dp.product_category_name_english AS category
        FROM marts.fact_orders fo
        JOIN marts.dim_customer dc ON dc.customer_unique_id = fo.customer_unique_id
        JOIN marts.fact_order_items foi ON foi.order_id = fo.order_id AND foi.order_item_id = 1
        JOIN marts.dim_seller ds ON ds.seller_id = foi.seller_id
        JOIN marts.dim_product dp ON dp.product_id = foi.product_id
        WHERE fo.is_delivered
          AND fo.n_distinct_sellers = 1
          AND fo.is_late IS NOT NULL
          AND fo.estimated_delivery_days IS NOT NULL
          AND dc.customer_latitude IS NOT NULL
          AND ds.seller_latitude IS NOT NULL
        ORDER BY fo.order_id
    """, engine)

    dfA["order_purchase_date"] = pd.to_datetime(dfA["order_purchase_date"])
    dfA["distance_km"] = haversine_km(dfA["customer_latitude"], dfA["customer_longitude"],
                                        dfA["seller_latitude"], dfA["seller_longitude"])
    dfA["customer_region"] = dfA["customer_state"].map(BR_REGION)
    dfA["seller_region"] = dfA["seller_state"].map(BR_REGION)
    dfA["is_cross_region"] = (dfA["customer_region"] != dfA["seller_region"]).astype(int)
    dfA["purchase_month"] = dfA["order_purchase_date"].dt.month
    dfA["purchase_dow"] = dfA["order_purchase_date"].dt.dayofweek
    dfA["freight_ratio"] = dfA["freight_value_total"] / dfA["order_total_value"]
    dfA["is_late"] = dfA["is_late"].astype(int)

    dfA = dfA.dropna(subset=["category"])
    top_catsA = dfA["category"].value_counts()
    top_catsA = top_catsA[top_catsA >= 500].index.tolist()
    dfA["category_grp"] = np.where(dfA["category"].isin(top_catsA), dfA["category"], "other")

    num_featsA = ["estimated_delivery_days", "distance_km", "order_total_value", "freight_ratio",
                  "n_items", "max_installments", "is_cross_region"]
    cat_featsA = ["primary_payment_type", "category_grp", "purchase_month", "purchase_dow"]

    X_A = build_X(dfA, num_featsA, cat_featsA)
    y_A = dfA["is_late"].values

    scalerA = StandardScaler()
    X_A_scaled = X_A.copy()
    X_A_scaled[num_featsA] = scalerA.fit_transform(X_A[num_featsA])

    # Final production model: retrained on the FULL population after validation in NB6
    # (held-out AUC=0.7422 / PR-AUC=0.2153, documented in notebooks/06_predictive_modeling.ipynb)
    rfA = RandomForestClassifier(n_estimators=200, max_depth=8, random_state=RANDOM_STATE,
                                   class_weight="balanced", n_jobs=-1)
    rfA.fit(X_A_scaled, y_A)
    dfA["predicted_late_risk"] = rfA.predict_proba(X_A_scaled)[:, 1]

    # decile 1 = highest predicted risk
    dfA["risk_decile"] = 10 - pd.qcut(dfA["predicted_late_risk"].rank(method="first"), 10, labels=False)
    dfA["risk_tier"] = dfA["risk_decile"].map(risk_tier)

    dfA = add_state_name(dfA, "customer_state")
    risk_scores_late_delivery = dfA[[
        "order_id", "order_purchase_date", "customer_state", "state_name", "customer_region", "category_grp",
        "order_total_value", "estimated_delivery_days", "distance_km", "freight_ratio",
        "is_late", "predicted_late_risk", "risk_decile", "risk_tier",
    ]].copy()
    write_csv(risk_scores_late_delivery, "risk_scores_late_delivery.csv")

    fiA_raw = pd.Series(rfA.feature_importances_, index=X_A_scaled.columns)
    feature_importance_model_a = group_importance(fiA_raw, num_featsA, cat_featsA)
    feature_importance_model_a["model"] = "Late Delivery Risk (Model A)"
    write_csv(feature_importance_model_a, "feature_importance_model_a.csv")

    # ----- Model B: negative-review risk (post-delivery features) -----
    dfB = pd.read_sql("""
        SELECT
            fo.order_id, fo.order_purchase_date, fo.order_total_value,
            fo.freight_value_total, fo.n_items, fo.n_distinct_sellers,
            fo.primary_payment_type, fo.max_installments,
            fo.delivery_delay_days, fo.is_late, fo.review_score,
            fo.customer_state,
            dp.product_category_name_english AS category
        FROM marts.fact_orders fo
        LEFT JOIN marts.fact_order_items foi ON foi.order_id = fo.order_id AND foi.order_item_id = 1
        LEFT JOIN marts.dim_product dp ON dp.product_id = foi.product_id
        WHERE fo.is_delivered
          AND fo.review_score IS NOT NULL
          AND fo.delivery_delay_days IS NOT NULL
        ORDER BY fo.order_id
    """, engine)

    dfB["order_purchase_date"] = pd.to_datetime(dfB["order_purchase_date"])
    dfB["customer_region"] = dfB["customer_state"].map(BR_REGION)
    dfB["purchase_month"] = dfB["order_purchase_date"].dt.month
    dfB["freight_ratio"] = dfB["freight_value_total"] / dfB["order_total_value"]
    dfB["is_late"] = dfB["is_late"].astype(int)
    dfB["is_negative"] = (dfB["review_score"] <= 2).astype(int)
    dfB["category"] = dfB["category"].fillna("unknown")

    top_catsB = dfB["category"].value_counts()
    top_catsB = top_catsB[top_catsB >= 500].index.tolist()
    dfB["category_grp"] = np.where(dfB["category"].isin(top_catsB), dfB["category"], "other")

    num_featsB = ["is_late", "delivery_delay_days", "order_total_value", "freight_ratio",
                  "n_items", "max_installments", "n_distinct_sellers"]
    cat_featsB = ["primary_payment_type", "category_grp", "customer_region", "purchase_month"]

    X_B = build_X(dfB, num_featsB, cat_featsB)
    y_B = dfB["is_negative"].values

    scalerB = StandardScaler()
    X_B_scaled = X_B.copy()
    X_B_scaled[num_featsB] = scalerB.fit_transform(X_B[num_featsB])

    # Final production model: retrained on the FULL population after validation in NB6
    # (held-out AUC=0.745 / PR-AUC=0.270, documented in notebooks/06_predictive_modeling.ipynb)
    rfB = RandomForestClassifier(n_estimators=200, max_depth=8, random_state=RANDOM_STATE,
                                   class_weight="balanced", n_jobs=-1)
    rfB.fit(X_B_scaled, y_B)
    dfB["predicted_negative_review_risk"] = rfB.predict_proba(X_B_scaled)[:, 1]

    dfB["risk_decile"] = 10 - pd.qcut(dfB["predicted_negative_review_risk"].rank(method="first"), 10, labels=False)
    dfB["risk_tier"] = dfB["risk_decile"].map(risk_tier)

    dfB = add_state_name(dfB, "customer_state")
    risk_scores_negative_review = dfB[[
        "order_id", "order_purchase_date", "customer_state", "state_name", "customer_region", "category_grp",
        "order_total_value", "is_late", "delivery_delay_days", "freight_ratio", "n_distinct_sellers",
        "review_score", "is_negative", "predicted_negative_review_risk", "risk_decile", "risk_tier",
    ]].copy()
    write_csv(risk_scores_negative_review, "risk_scores_negative_review.csv")

    fiB_raw = pd.Series(rfB.feature_importances_, index=X_B_scaled.columns)
    feature_importance_model_b = group_importance(fiB_raw, num_featsB, cat_featsB)
    feature_importance_model_b["model"] = "Negative Review Risk (Model B)"
    write_csv(feature_importance_model_b, "feature_importance_model_b.csv")


# ---------------------------------------------------------------------------
# Drill-through detail extracts (shared across pages)
# ---------------------------------------------------------------------------
def build_detail_extracts(orders: pd.DataFrame, items: pd.DataFrame) -> None:
    orders = add_state_name(orders, "customer_state", "customer_state_name")
    orders = add_state_name(orders, "seller_state", "seller_state_name")
    orders_detail = orders[[
        "order_id", "customer_unique_id", "customer_state", "customer_state_name", "customer_city", "customer_region",
        "order_status", "order_purchase_date", "purchase_year", "purchase_month", "purchase_dow",
        "n_items", "n_distinct_sellers", "n_distinct_products",
        "order_total_value", "items_price_total", "freight_value_total", "freight_ratio",
        "primary_payment_type", "max_installments",
        "estimated_delivery_days", "actual_delivery_days", "delivery_delay_days",
        "is_late", "is_delivered", "is_canceled",
        "review_score", "has_review", "is_negative_review",
        "category", "category_grp",
        "seller_id", "seller_state", "seller_state_name", "seller_region", "is_cross_region", "distance_km",
    ]].copy()
    write_csv(orders_detail, "orders_detail.csv")

    items = add_state_name(items, "customer_state", "customer_state_name")
    items = add_state_name(items, "seller_state", "seller_state_name")
    items_detail = items[[
        "order_id", "order_item_id", "product_id", "category", "category_grp",
        "seller_id", "seller_state", "seller_state_name", "seller_region",
        "customer_state", "customer_state_name", "customer_region", "order_purchase_date", "order_status",
        "price", "freight_value", "item_total_value",
    ]].copy()
    write_csv(items_detail, "order_items_detail.csv")


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------
def main() -> None:
    EXTRACTS_DIR.mkdir(parents=True, exist_ok=True)
    engine = get_engine()

    log.info("Loading base order/item extracts...")
    orders = load_orders(engine)
    items = load_items(engine)
    log.info("orders: %s rows, items: %s rows", f"{len(orders):,}", f"{len(items):,}")

    log.info("Building Page 1 -- Executive Overview")
    build_page1_executive(orders)

    log.info("Building Page 2 -- Sales & Category Performance")
    build_page2_category(orders, items)

    log.info("Building Page 3 -- Geography")
    build_page3_geography(orders, items)

    log.info("Building Page 4 -- Delivery & Fulfillment Operations")
    build_page4_fulfillment(engine, orders)

    log.info("Building Page 5 -- Customer Segmentation (RFM + K-Means + PCA)")
    build_page5_segmentation(engine)

    log.info("Building Page 6 -- Seller Marketplace")
    build_page6_sellers(orders, items)

    log.info("Building Page 7 -- Predictive Risk Scoring (this trains 2 RandomForests, ~1-2 min)")
    build_page7_risk_scores(engine)

    log.info("Building drill-through detail extracts")
    build_detail_extracts(orders, items)

    n_files = len(list(EXTRACTS_DIR.glob("*.csv")))
    log.info("Done. %d CSV extracts written to %s", n_files, EXTRACTS_DIR)


if __name__ == "__main__":
    main()


# ---------------------------------------------------------------------------
# EXTRACT CATALOG (24 files)
# ---------------------------------------------------------------------------
# Page 1 - Executive Overview
#   monthly_kpis.csv              monthly GMV/orders/AOV/OTD/reviews/repeat mix, Sep16-Oct18
#   seasonality_analysis.csv      trailing-3mo-avg de-trended GMV, Jan17-Aug18
#   kpi_summary.csv                1-row headline KPI tile data
#
# Page 2 - Sales & Category Performance
#   category_summary.csv          revenue/units/quality Pareto by product category
#   category_monthly_mix.csv      top-10 category revenue mix over time
#   top_products.csv               top 50 products by revenue
#
# Page 3 - Geography
#   geo_customer_state_summary.csv  demand-side GMV/OTD/review by customer state
#   geo_seller_state_summary.csv    supply-side revenue by seller state
#   region_flow_matrix.csv           customer-region x seller-region flow & OTD
#
# Page 4 - Delivery & Fulfillment Operations
#   cycle_time_stages.csv          approval/carrier/transit/end-to-end duration stats
#   delay_bucket_vs_review.csv      delivery delay bucket vs review score
#   fulfillment_weekly_2018.csv     Jan-Apr 2018 weekly OTD anomaly
#   anomaly_state_comparison.csv    state-level OTD, normal vs spike period
#
# Page 5 - Customer Segmentation
#   customer_segments.csv          customer-grain RFM + K-Means cluster + PCA coords
#   segment_profile_summary.csv     4-cluster profile (named segments)
#   rfm_segment_summary.csv         5 RFM-quintile segment summary
#
# Page 6 - Seller Marketplace
#   seller_scorecard.csv           every seller: revenue, OTD, review, decile
#   seller_pareto_deciles.csv       seller revenue concentration by decile
#
# Page 7 - Predictive Risk Scoring
#   risk_scores_late_delivery.csv   Model A: order-time late-delivery risk score
#   risk_scores_negative_review.csv Model B: post-delivery negative-review risk score
#   feature_importance_model_a.csv  Model A grouped feature importances
#   feature_importance_model_b.csv  Model B grouped feature importances
#
# Drill-through detail (cross-page)
#   orders_detail.csv               order-grain detail (99,441 rows)
#   order_items_detail.csv          line-item-grain detail (112,650 rows)
