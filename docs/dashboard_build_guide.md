# Tableau Dashboard Build Guide

**Workbook:** Olist E-Commerce Analytics — 7-page interactive dashboard
**Audience:** whoever builds/maintains the Tableau Public workbook (could be future-you)
**Inputs:** the 24 CSVs in `dashboard/extracts/`, produced by `etl/export_dashboard_extracts.py`
**Companion docs:** `docs/data_quality_report.md`, `notebooks/0{1-6}_*.ipynb` (source of every finding cited below)

This guide is a build spec, not a tutorial — it assumes familiarity with Tableau Desktop
(connecting to text files, the Marks card, calculated fields, parameters, dashboard
actions). For each of the 7 pages it gives: the business question, the data source(s),
a sheet-by-sheet breakdown (chart type, shelves, calculated fields, sort/filter,
color), the dashboard layout, and the interactivity (filter actions, navigation).

A **Master Calculated Fields Reference** (Section 4) collects every formula referenced
in the page specs in one place, organized by source CSV, so you can build them all up
front before laying out sheets.

---

## 0. Before you start — two conventions that will save you rework

### 0.1 The `pct_*` vs. `is_*` number-formatting rule

Every extract was audited for unit consistency before this guide was written (one
inconsistency — `customer_segments.pct_late` / `segment_profile_summary.pct_late` was
on a 0–1 scale while every other `pct_*` field was 0–100 — was found and fixed in
`export_dashboard_extracts.py`; all 24 CSVs were regenerated and now follow a single
convention). The convention is:

| Field pattern | Scale | Example | Tableau format to apply |
|---|---|---|---|
| Any field named `pct_*`, `*_pct`, or `*_pct_*` (e.g. `pct_late`, `gmv_mom_pct`, `pct_of_total_gmv`, `repeat_rate_pct`, `pct_repeat`, `pct_1star`, `pct_above_trailing_avg`, `pct_of_total_importance`) | **0–100** (already a percentage value — `8.11` means `8.11%`) | `pct_late = 8.11` | **Custom number format** `0.0\%` (or `0.0"%"`). **Do NOT** use Tableau's built-in *Percentage* format — it multiplies by 100 again and would render `811.0%`. |
| Any field named `is_*` (`is_late`, `is_negative`, `is_repeat`, `is_cross_region`, `is_delivered`, `is_canceled`, `has_review`, `is_full_month`, `is_seasonal_spike`) | **0/1 flag** (boolean or integer) | `is_late = 0 or 1` | When aggregated with `AVG()` (e.g. `AVG([Is Late])` → a "late rate"), the result is **0–1** — apply Tableau's built-in **Percentage** format (this *is* the correct case for it: `0.081` → `8.1%`). |
| `predicted_late_risk`, `predicted_negative_review_risk` | **0–1** (model probability) | `0.396` | Built-in **Percentage** format → `39.6%` |

Get this wrong and every KPI tile reads `811%` instead of `8.1%` — the single most
common Tableau-from-CSV mistake. Apply the format at the **data source field** level
(right-click the field in the Data pane → Default Properties → Number Format) so every
new sheet inherits it automatically.

### 0.2 Currency, distance, and day formats

| Field pattern | Example fields | Format |
|---|---|---|
| Monetary (R$) | `gmv`, `revenue`, `monetary`, `total_gmv`, `total_revenue`, `aov`, `avg_order_value`, `decile_revenue`, `avg_monetary`, `order_total_value` | Custom Currency, prefix `R$`, thousands separator. Large totals (`gmv`, `total_gmv`, `total_revenue`, `decile_revenue`): `R$ #,##0`. Per-order/per-customer values (`aov`, `avg_order_value`, `monetary`, `revenue` in `top_products`): `R$ #,##0.00`. |
| Distance | `distance_km`, `avg_distance_km` | `#,##0 "km"` |
| Days | `recency_days`, `*_delay_days`, `*_delivery_days`, `*_handoff_days`, `*_transit_days`, `avg_value`/`median_value`/`p90_value` in `cycle_time_stages` (when `unit = days`) | `#,##0.0 "days"` |
| Hours | `cycle_time_stages` rows where `unit = hours` | `#,##0.0 "hrs"` |

---

## 1. Workbook architecture

- **One Tableau workbook, 7 dashboards** (one per page below), each sized **1300 × 850 px,
  Fixed Size** — consistent canvas across the workbook so navigation buttons line up.
- **24 separate data sources**, one per CSV, each as a **Text File (Extract)** connection
  (Tableau Public requires extracts — no live file connections survive publishing).
  Do **not** build Tableau Relationships/Joins between them: the 24 extracts span wildly
  different grains (1 row in `kpi_summary` vs. 99,441 rows in `orders_detail`).
  Cross-source interactivity is handled entirely with **dashboard filter actions**
  (Section 5), which work across data sources as long as the field names/values line up.
- **Title bar convention** for every dashboard: `Olist E-Commerce Analytics  |  Page N — <Name>`
  as the dashboard title, with a one-line subtitle stating the business question the
  page answers (use a Text object under the title).
- **Navigation**: each dashboard gets a row of 7 small **Navigation objects** (Dashboard →
  Navigation) along the top-right, one per page, with the current page's button
  visually disabled/highlighted. Build all 7 dashboards first, then add navigation last
  (Tableau navigation buttons need their target dashboards to already exist).

---

## 2. Data source setup checklist

For each of the 24 CSVs in `dashboard/extracts/`:

1. **Connect** → Text File → select the CSV. Tableau auto-detects headers and types.
2. **Verify date fields are typed as Date** (not String). All date columns in these
   extracts are ISO `YYYY-MM-DD` and auto-detect correctly, but double-check:
   `month` (monthly_kpis, seasonality_analysis, category_monthly_mix), `week`
   (fulfillment_weekly_2018), `order_purchase_date` (risk_scores_*, orders_detail,
   order_items_detail), `last_order_date` (customer_segments), `date_range_start` /
   `date_range_end` (kpi_summary).
3. **Apply the number formats from Section 0** to every `pct_*`, `is_*`,
   `predicted_*_risk`, monetary, distance, and day field — do this once per data
   source, immediately after connecting.
4. **Set Geographic Roles** (only needed on the 4 sources used for maps —
   `geo_customer_state_summary`, `geo_seller_state_summary`,
   `risk_scores_late_delivery`, `risk_scores_negative_review`):
   - `state_name` (or `customer_state_name` / `seller_state_name`) → Geographic Role →
     **State/Province**.
   - Create a calculated field `Country` = `"Brazil"` (a string constant) → Geographic
     Role → **Country/Region**. Tableau's built-in geocoder recognizes Brazilian state
     names (`São Paulo`, `Rio de Janeiro`, `Amapá`, `Espírito Santo`, etc. — this is
     exactly why `export_dashboard_extracts.py` added the `state_name` columns instead
     of relying on a shapefile), but several Brazilian state names collide with
     places in other countries (e.g. **Distrito Federal** also exists in Mexico and
     Venezuela). Placing `Country = "Brazil"` on the Detail shelf alongside
     `state_name` resolves the ambiguity. This calc field must be created
     independently in **each** of the 4 sources (Tableau calc fields are
     per-data-source).
5. **Extract** (Data → [source name] → Extract → Compute Now) before publishing.

---

## 3. Global style guide

### 3.1 Region color palette (used on Pages 1, 3, 4, 5, 6, 7 wherever `region` /
`customer_region` / `seller_region` appears)

Derived from seaborn's "deep" palette (matches the color language already used in the
notebook charts, for visual continuity between the EDA notebooks and the dashboard):

| Region | Hex | Swatch |
|---|---|---|
| North | `#4c72b0` | navy blue |
| Northeast | `#dd8452` | orange |
| Central-West | `#55a868` | green |
| Southeast | `#c44e52` | red |
| South | `#8172b3` | purple |

Set this once via **Analysis → Edit Colors** on any sheet using `region` and choose
"Assign Palette" → pick each color manually with the hex codes above (Tableau's color
picker accepts hex input). Once set for one sheet on a given data source, it persists
for that field on that data source, but **must be re-set on each data source** that
has a `region`/`customer_region`/`seller_region` field.

### 3.2 Customer segment colors (Page 5 — `segment` field, 4 values)

| Segment | Hex | Rationale |
|---|---|---|
| Core High-Value | `#4c72b0` | "primary/best" blue — 44.5% of customers, 69.5% of revenue |
| Loyal Repeat Customers | `#55a868` | "good" green — only 2.5% of customers but 71.5% repeat-purchase rate |
| At-Risk: Late & Unhappy | `#c44e52` | "danger" red — 99.7% late-order rate, avg review 2.55★ |
| Budget Satisfied | `#ccb974` | neutral gold — 45.1% of customers, low ticket, high satisfaction |

### 3.3 RFM segment colors (Page 5 — `rfm_segment` field, 5 values, in
`rfm_segment_summary.csv` and `customer_segments.csv`)

| RFM Segment | Hex |
|---|---|
| Champions (recent + high spend) | `#4c72b0` |
| High-Value Lapsed (win-back priority) | `#dd8452` |
| Mid-Value | `#8c8c8c` |
| New/Recent Low-Spend | `#64b5cd` |
| Low-Value Lapsed | `#937860` |

(Champions sharing `#4c72b0` with Core High-Value is intentional — both are the "best"
segment in their respective taxonomies, reinforcing "blue = best" as a recurring
visual language across Page 5.)

### 3.4 Risk tier colors (Page 7 — `risk_tier` field, 3 values)

| Risk Tier | Hex |
|---|---|
| High Risk (top 20%) | `#c44e52` |
| Medium Risk (next 30%) | `#dd8452` |
| Low Risk (bottom 50%) | `#55a868` |

### 3.5 Delivery delay-bucket colors (Page 4 — `delay_bucket` field, 5 values)

A green→gray→amber→orange→red "good to bad" progression:

| Delay Bucket | Hex |
|---|---|
| 1. Early (2+ days ahead) | `#55a868` |
| 2. On-time (0-1 day ahead) | `#8c8c8c` |
| 3. Late 1-3 days | `#ccb974` |
| 4. Late 4-7 days | `#dd8452` |
| 5. Late 8+ days | `#c44e52` |

(The leading `"1. " … "5. "` numbering in the source data was deliberately added in
`export_dashboard_extracts.py` so Tableau's default alphabetical sort already produces
the correct severity order — no manual sort needed.)

### 3.6 Typography & sizing

- Keep Tableau's default font family ("Tableau Book" / "Tableau Bold") — custom fonts
  are not guaranteed to render for Tableau Public viewers without the font installed.
- Dashboard title: 18–20pt bold. Subtitle/business-question text: 11pt regular, gray
  (`#595959`). Sheet titles: 12–13pt bold. Axis/label text: 9–10pt.
- Every sheet gets a **caption or subtitle** stating what it shows in plain language
  (e.g. "Late-delivery rate by state — 8x variation, concentrated in the Northeast")
  — these double as the dashboard's narrative for a recruiter clicking through without
  narration.

---

## 4. Master calculated fields reference

Build these before laying out sheets. Grouped by the data source they belong to.
Field names in `[Brackets]` are Tableau's auto-generated names from the CSV header
(Tableau title-cases and replaces underscores with spaces, e.g. `pct_late` →
`[Pct Late]`).

### 4.1 `kpi_summary.csv`

```
On-Time Delivery Rate
= 100 - [Pct Late Overall]
```
Format: `0.0\%`. Used for the Page 1 "On-Time Rate" KPI tile.

### 4.2 `monthly_kpis.csv`

```
Growth Direction
= IF [Gmv Mom Pct] >= 0 THEN "Growth" ELSE "Decline" END
```
Used to color the MoM growth bar chart (Growth = `#55a868`, Decline = `#c44e52`).

### 4.3 `geo_customer_state_summary.csv`

```
Country
= "Brazil"
```
Geographic Role = Country/Region (see Section 2, step 4).

```
Map Metric Value
= CASE [Map Metric]
    WHEN "GMV (R$)"             THEN [Gmv]
    WHEN "Late Delivery Rate"   THEN [Pct Late]
    WHEN "Avg Review Score"     THEN [Avg Review Score]
    WHEN "Avg Delivery Days"    THEN [Avg Actual Delivery Days]
  END
```
Depends on a **String parameter** `Map Metric` with the 4 values above (default "GMV
(R$)"). Powers the parameter-driven choropleth on Page 3 (Sheet 1).

### 4.4 `geo_seller_state_summary.csv`

```
Country
= "Brazil"
```

### 4.5 `category_summary.csv`

```
Top-10 Label
= IF [Revenue Rank] <= 10 THEN [Category] END
```
Used to label only the top-10 categories on the quality-quadrant scatter (Page 2,
Sheet 2) to avoid label clutter across 74 categories.

### 4.6 `fulfillment_weekly_2018.csv`

```
Is Anomaly Period
= [Week] >= #2018-02-12# AND [Week] <= #2018-03-26#
```
Used to shade/highlight the Feb–Mar 2018 fulfillment-crisis weeks on the weekly trend
line (Page 4, Sheet 3). Adjust the exact boundary dates to match the spike window
documented in NB3/NB6 if you want pixel-exact alignment with the notebook charts.

### 4.7 `risk_scores_late_delivery.csv`

```
Country
= "Brazil"
```

```
Late Rate
= AVG([Is Late])
```
Format: built-in **Percentage**. This is the y-axis of the Model A decile lift chart
(Page 7, Sheet 1).

### 4.8 `risk_scores_negative_review.csv`

```
Country
= "Brazil"
```

```
Negative Review Rate
= AVG([Is Negative])
```
Format: built-in **Percentage**. y-axis of the Model B decile lift chart (Page 7,
Sheet 3).

### 4.9 `feature_importance_model_a.csv` AND `feature_importance_model_b.csv`

Create this **identical** calculated field in both data sources (the feature sets
overlap but aren't identical, so the `ELSE` branch covers any feature not explicitly
named):

```
Feature Label
= CASE [Feature]
    WHEN "purchase_month"          THEN "Purchase Month"
    WHEN "estimated_delivery_days" THEN "Estimated Delivery Window (days)"
    WHEN "distance_km"              THEN "Customer-Seller Distance (km)"
    WHEN "category_grp"             THEN "Product Category Group"
    WHEN "order_total_value"        THEN "Order Value (R$)"
    WHEN "freight_ratio"            THEN "Freight / Order Value Ratio"
    WHEN "purchase_dow"             THEN "Day of Week"
    WHEN "is_cross_region"          THEN "Cross-Region Fulfillment"
    WHEN "max_installments"         THEN "Payment Installments"
    WHEN "primary_payment_type"     THEN "Payment Type"
    WHEN "n_items"                  THEN "Items per Order"
    WHEN "delivery_delay_days"      THEN "Delivery Delay (days)"
    WHEN "is_late"                  THEN "Order Was Late"
    WHEN "n_distinct_sellers"       THEN "Distinct Sellers per Order"
    WHEN "customer_region"          THEN "Customer Region"
    ELSE [Feature]
  END
```

---

## 5. Page-by-page build specs

---

### Page 1 — Executive Overview

**Business question:** "How is the business performing overall, and what does the
top-line trend look like?"

**Data sources:** `monthly_kpis.csv` (24 rows), `seasonality_analysis.csv` (17 rows),
`kpi_summary.csv` (1 row)

#### Sheet 1.1 — KPI tiles (Big Number text sheets)

Build **6 separate single-value text sheets** from `kpi_summary.csv` (1 row, so every
field is a literal constant — `SUM()` of a single row returns that row's value):

| Tile | Field | Format |
|---|---|---|
| Total GMV | `SUM([Total Gmv])` | `R$ #,##0` → "R$ 15,735,527" |
| Avg Order Value | `SUM([Aov])` | `R$ #,##0.00` → "R$ 160.23" |
| Total Orders | `SUM([Total Orders])` | `#,##0` → "99,441" |
| On-Time Delivery Rate | `SUM([On-Time Delivery Rate])` (calc 4.1) | `0.0\%` → "91.9%" |
| Avg Review Score | `SUM([Avg Review Score Overall])` | `0.00 "★"` → "4.12 ★" |
| Repeat Customer Rate | `SUM([Repeat Rate Pct])` | `0.0\%` → "3.0%" |

Each tile: drop the measure on the Text shelf, set mark type to "Square" with no
border/fill, font size ~28pt bold for the number. Add a Text object below each with
the label ("Total GMV", etc.) at 10pt gray. Arrange all 6 in a horizontal container
across the top of the dashboard. Add one more small text object with
`[Date Range Start]` – `[Date Range End]` as the data window ("Sep 2016 – Sep 2018").

#### Sheet 1.2 — Monthly GMV Trend with 3-Month Moving Average

- Data source: `monthly_kpis.csv`
- **Filter**: `[Is Full Month] = True` (drops the partial Sep-2016 and Sep-2018
  months, leaving a clean Jan-2017 → Aug-2018 series — 20 contiguous months)
- Columns: `[Month]` (continuous, exact date — green pill)
- Rows: `SUM([Gmv])` — Mark: **Area**, color `#4c72b0` at ~40% opacity
- Dual axis: `SUM([Gmv 3Mo Moving Avg])` — Mark: **Line**, color `#c44e52`, dashed,
  2px. Synchronize axes.
- Tooltip: include `[N Orders]`, `[Aov]`, `[Gmv Mom Pct]` (formatted `0.0\%`)
- Title: "Monthly GMV — with 3-Month Moving Average"
- Subtitle/caption: cross-reference NB2 — strong Jun-2017–Jul-2018 growth trend
  (~R$46K/month, R²=0.67; Finding #20), Nov-2017 spike visible (Finding #18).

#### Sheet 1.3 — Cumulative GMV

- Data source: `monthly_kpis.csv`, same filter (`Is Full Month = True`)
- Columns: `[Month]` (continuous), Rows: `SUM([Cumulative Gmv])`
- Mark: Area, color `#4c72b0`, 60% opacity
- Format axis as `R$ #,##0,,"M"` (millions) if it renders cleanly, else `R$ #,##0`

#### Sheet 1.4 — GMV Month-over-Month Growth %

- Data source: `monthly_kpis.csv`, filter `Is Full Month = True` AND
  `[Gmv Mom Pct]` is not null (excludes the first month, which has no prior month)
- Columns: `[Month]` (discrete or continuous, your call — discrete gives cleaner
  bar spacing)
- Rows: `SUM([Gmv Mom Pct])`, format `0.0\%`
- Color: `[Growth Direction]` (calc 4.2) → Growth `#55a868`, Decline `#c44e52`
- Add a **reference line** at 0 (constant, solid black, label "0%")

#### Sheet 1.5 — Seasonality: % Above/Below Trailing 3-Month Average

- Data source: `seasonality_analysis.csv`
- Columns: `[Month]` (discrete)
- Rows: `[Pct Above Trailing Avg]`, format `0.0\%`
- Color: `[Is Seasonal Spike]` (boolean) → True `#c44e52`, False `#8c8c8c`
- Reference line at 0
- Tooltip: `[Gmv]`, `[Trailing 3Mo Avg Gmv]`
- Caption: "Nov-2017 GMV is 64% above its trailing 3-month average — the dataset's one
  exceptional month (Black Friday; corroborated independently by STL decomposition in
  NB2, Finding #18)."

#### Dashboard 1 layout

```
┌─────────────────────────────────────────────────────────────────┐
│  Olist E-Commerce Analytics  |  Page 1 — Executive Overview       │  [nav row]
│  "How is the business performing overall?"   Sep 2016 – Sep 2018  │
├─────────┬─────────┬─────────┬─────────┬─────────┬─────────────────┤
│  GMV    │  AOV    │ Orders  │On-Time% │ Review★ │  Repeat %        │  (Sheet 1.1 x6)
├─────────┴─────────┴─────────┴─────────┴─────────┴─────────────────┤
│                                                    │                │
│   Sheet 1.2 — Monthly GMV + 3mo MA  (2/3 width)   │  Sheet 1.3      │
│                                                    │  Cumulative GMV │
│                                                    │  (1/3 width)    │
├────────────────────────────────┬─────────────────────────────────┤
│  Sheet 1.4 — MoM Growth %        │  Sheet 1.5 — Seasonality        │
└────────────────────────────────┴─────────────────────────────────┘
```

No dashboard actions needed on this page — it's the company-level landing page.

---

### Page 2 — Sales & Category Performance

**Business question:** "Where does revenue come from, and which categories combine
high revenue with good delivery/satisfaction — vs. which need attention?"

**Data sources:** `category_summary.csv` (74 categories), `category_monthly_mix.csv`
(220 rows = top-10 categories + "other", × 22 months), `top_products.csv` (top 50
products)

#### Sheet 2.1 — Category Revenue Pareto

- Data source: `category_summary.csv`
- Filter: `[Revenue Rank] <= 20` (top 20 of 74 categories — covers the steep part of
  the curve)
- Columns: `[Category]`, sorted by `[Revenue Rank]` ascending
- Rows (dual axis):
  - Bar: `SUM([Revenue])`, color `#4c72b0`
  - Line: `AVG([Cumulative Pct Of Revenue])` (one value per category, so AVG = the
    value), color `#c44e52`, right axis 0–100%, format `0\%`
- Reference line on the right axis at 80% (label "80% of revenue")
- Tooltip: `[Pct Of Total Revenue]`, `[N Items Sold]`, `[Avg Review Score]`,
  `[Pct Late]`
- Caption: "Top 9 categories ≈ 50% of revenue; top 20 ≈ 80% — a classic Pareto
  distribution."

#### Sheet 2.2 — Category Quality Quadrant

- Data source: `category_summary.csv`
- Filter: `[Revenue Rank] <= 30`
- Columns: `[Pct Late]` (X axis, format `0.0\%`)
- Rows: `[Avg Review Score]` (Y axis)
- Size: `SUM([Revenue])`
- Color: single color `#4c72b0` at 60% opacity (74→30 categories is still a lot of
  distinct colors; size + reference-line quadrants carry the story instead)
- Label: `[Top-10 Label]` (calc 4.5) — only top-10-by-revenue categories get a
  text label, avoiding clutter
- **Reference lines**: Average line for `[Pct Late]` (vertical, gray dashed) and
  Average line for `[Avg Review Score]` (horizontal, gray dashed) — these split the
  view into 4 quadrants:
  - top-left = low late-rate / high review = "Star categories"
  - bottom-left = low late-rate / low review = category-intrinsic dissatisfaction
    (independent of delivery — ties to NB4 Finding #33, e.g. `office_furniture`)
  - top-right / bottom-right = high late-rate quadrants
- Caption: "Bubble size = revenue. Categories below the horizontal line have
  below-average reviews even when delivered on time (Finding #33) — a
  product/expectations issue, not a logistics one."

#### Sheet 2.3 — Category Monthly Revenue Mix

- Data source: `category_monthly_mix.csv`
- Columns: `[Month]` (continuous)
- Rows: `SUM([Revenue])`, Mark: **Area**, **Stack marks = On**
- Color: `[Category Mix]` (top-10 category names + "other") — use a categorical
  palette (Tableau default "Tableau 20" is fine here since this is a different field
  than `region`/`segment`; don't force the deep palette onto 11 values)
- Tooltip: `[Share Of Month]` (format `0.0\%`), `[N Items Sold]`

#### Sheet 2.4 — Top Products

- Data source: `top_products.csv`
- Filter: `[Revenue Rank] <= 15`
- Columns: `SUM([Revenue])`
- Rows: `[Product Id]` sorted by `[Revenue Rank]` ascending. (Product IDs are opaque
  hashes — consider concatenating `[Category] + " (" + LEFT([Product Id], 6) + "…)"`
  as a display label calc if you want more legible bars; otherwise rely on the
  tooltip.)
- Color: `[Category]`
- Tooltip: `[Avg Price]`, `[N Sold]`, `[Category]`

#### Dashboard 2 layout

```
┌─────────────────────────────────────────────────────────────────┐
│  Page 2 — Sales & Category Performance               [nav row]    │
│  "Where does revenue come from, and which categories perform?"    │
├─────────────────────────────────────────────────────────────────┤
│              Sheet 2.1 — Category Revenue Pareto (full width)     │
├───────────────────────────────────┬───────────────────────────────┤
│  Sheet 2.2 — Quality Quadrant       │  Sheet 2.3 — Monthly Mix       │
│                                      │  (stacked area)                │
├───────────────────────────────────┴───────────────────────────────┤
│              Sheet 2.4 — Top 15 Products (full width)              │
└─────────────────────────────────────────────────────────────────┘
```

#### Dashboard actions

- **Filter action**: Source = Sheet 2.1 (Pareto), Run on **Select**, Target = Sheet
  2.4 (Top Products), Field mapping `category` → `category`. Clicking a category bar
  filters the Top Products list to that category. Add a "Show all" reset by enabling
  "Clearing the selection will: Show all values".

---

### Page 3 — Geography

**Business question:** "Where are our customers and sellers, and where does delivery
performance break down geographically?"

**Data sources:** `geo_customer_state_summary.csv` (27 states),
`geo_seller_state_summary.csv` (23 states), `region_flow_matrix.csv` (23 rows)

#### Sheet 3.1 — Parameter-driven Customer Choropleth

- Data source: `geo_customer_state_summary.csv`
- **Parameter** `Map Metric` (String, list): `"GMV (R$)"`, `"Late Delivery Rate"`,
  `"Avg Review Score"`, `"Avg Delivery Days"` — default `"GMV (R$)"`
- Calc field `Map Metric Value` (4.3)
- Detail: `[State Name]` (geo role State/Province), `[Country]` (geo role
  Country/Region, calc 4.3 — "Brazil")
- Color: `SUM([Map Metric Value])`
  - When `Map Metric = "GMV (R$)"`: sequential blue ramp, format `R$ #,##0`
  - When `Map Metric = "Late Delivery Rate"`: sequential **Orange-Red** ramp (reversed
    so higher = darker/worse), format `0.0\%`
  - When `Map Metric = "Avg Review Score"`: diverging **Red-Green** ramp centered at
    4.116 (the overall average from `kpi_summary`), format `0.00`
  - When `Map Metric = "Avg Delivery Days"`: sequential ramp, format `#,##0.0 "days"`

  (Tableau applies one color encoding per field; since the *field* is always
  `Map Metric Value`, you'll pick one ramp that works reasonably across all 4 modes —
  e.g. a single Orange-to-Blue diverging ramp — OR build 4 near-identical sheets, one
  per metric, each with its own optimal ramp, and use a **parameter-controlled sheet
  swap** (show/hide containers based on `Map Metric`). For a portfolio piece, 4
  dedicated small-multiple maps (Sheet 3.1a–d below) are more visually impressive and
  avoid the color-ramp compromise — recommended primary approach.)

**Recommended: build 4 small-multiple maps instead of 1 parameter-driven map:**

| Sheet | Color field | Ramp | Cross-reference |
|---|---|---|---|
| 3.1a GMV by State | `SUM([Gmv])` | Sequential Blue, `R$ #,##0` | Finding #23 (SP=37.4% of GMV; top 5 states=73.1%) |
| 3.1b Late Rate by State | `[Pct Late]` | Sequential Orange-Red (reversed) | Finding #24 (2.9% RO → 23.9% AL, Northeast cluster ≥14%) |
| 3.1c Avg Review by State | `[Avg Review Score]` | Diverging Red-Green, center 4.116 | Finding #26 (r=-0.79 with `pct_late`) |
| 3.1d Avg Delivery Days by State | `[Avg Actual Delivery Days]` | Sequential Blue-to-Purple | supports 3.1b |

Each: Mark type **Map** (filled), Detail = `[State Name]` + `[Country]`, Tooltip
includes `customer_state`, `n_customers`, `n_orders`, `aov`, `pct_of_total_gmv`.
Arrange as a 2×2 grid — this is the visual centerpiece of the page.

#### Sheet 3.2 — Seller Revenue by State

- Data source: `geo_seller_state_summary.csv`
- Same map setup (own `Country` = "Brazil" calc, `[State Name]` geo role)
- Color: `SUM([Revenue])`, sequential Green ramp
- Tooltip: `n_sellers`, `n_items`, `pct_of_total_revenue`
- Caption: "Seller supply is even more concentrated than demand (NB3 Finding #29) —
  compare against Sheet 3.1a."

#### Sheet 3.3 — Cross-Region Fulfillment Matrix

- Data source: `region_flow_matrix.csv`
- Columns: `[Seller Region]`, Rows: `[Customer Region]`
- Mark type: **Square** (highlight table style)
- Color: `[Pct Late]`, sequential Orange-Red, format `0.0\%`
- Label: `[N Orders]` (format `#,##0`)
- Tooltip: `[Avg Distance Km]`, `[Avg Freight Ratio]`, `[Is Cross Region]`
- Caption: "64% of single-seller orders are fulfilled cross-state, taking ~1.9x longer
  and costing ~75% more freight (NB3 Finding #28)."

#### Sheet 3.4 — Top States Ranked Bar

- Data source: `geo_customer_state_summary.csv`
- Columns: `SUM([Gmv])`
- Rows: `[Customer State]`, sorted descending by `SUM([Gmv])` (or by `[Gmv Rank]`)
- Color: `[Region]` (region palette, Section 3.1)
- Filter: top 10 by `[Gmv Rank]`
- Label: `[Pct Of Total Gmv]` (format `0.0\%`) at the end of each bar

#### Dashboard 3 layout

```
┌─────────────────────────────────────────────────────────────────┐
│  Page 3 — Geography                                   [nav row]   │
│  "Where are our customers/sellers, and where does delivery break  │
│   down geographically?"                                            │
├──────────────────────────┬──────────────────────────────────────┤
│  3.1a GMV by State        │  3.1b Late Rate by State               │
├──────────────────────────┼──────────────────────────────────────┤
│  3.1c Avg Review by State │  3.1d Avg Delivery Days by State       │
├──────────────────────────┴──────────────────────────────────────┤
│  3.3 Cross-Region Fulfillment Matrix  │  3.2 Seller Revenue Map    │
│  (5x5 heatmap)                         │  + 3.4 Top States bar      │
└────────────────────────────────────────────────────────────────┘
```

#### Dashboard actions

- **Filter action**: Source = Sheet 3.1a (or any of the 4 maps — set "Run action on:
  Select" for all 4 so clicking any map filters consistently), Target = Sheet 3.4
  (Top States bar), Field `customer_state` → `customer_state`.
- **Filter action**: Source = Sheet 3.4 (Top States bar), Target = Sheet 3.3 (Cross-
  Region Matrix), Field mapping `region` → `customer_region` (Tableau lets you map
  differently-named fields in the Edit Filter Action dialog). Clicking a state
  highlights its region's row in the cross-region matrix.

---

### Page 4 — Delivery & Fulfillment Operations

**Business question:** "Where does fulfillment time go, how does delay translate into
dissatisfaction, and what happened during the Feb-Mar 2018 anomaly?"

**Data sources:** `cycle_time_stages.csv` (4 rows), `delay_bucket_vs_review.csv`
(5 rows), `fulfillment_weekly_2018.csv` (13 rows), `anomaly_state_comparison.csv`
(48 rows = 24 states × 2 periods)

#### Sheet 4.1 — Order Fulfillment Cycle Time

- Data source: `cycle_time_stages.csv`
- Rows: `[Stage]`, sorted by `[Stage Order]` (1→4: approval, carrier handoff, shipping
  transit, end-to-end)
- Columns: `SUM([Avg Value])`, Mark: **Bar**, color `#4c72b0`
- Add `[Median Value]` and `[P90 Value]` to the **Tooltip** (don't try to overlay them
  as marks — the `unit` differs between rows: stage 1 is in **hours**, stages 2–4 are
  in **days**. Mixing units on one axis is misleading. Either (a) keep everything in
  the tooltip with `unit` shown, or (b) convert stage 1 to days in a calc field
  `[Avg Value] / 24` if `[Unit] = "hours"` for visual consistency on the bar — but then
  clearly label the axis "days (approval converted from hours)").
- Caption: "Shipping transit (carrier → customer) is the dominant stage at 9.33 days
  avg / 7.1 days median — more than 2x the carrier-handoff stage. Approval is fast on
  median (0.34 hrs) but has a long right tail (avg 10.4 hrs, p90 34.7 hrs)."

#### Sheet 4.2 — Delay Bucket vs. Review Score (the "cliff")

- Data source: `delay_bucket_vs_review.csv`
- Columns: `[Delay Bucket]` (discrete — the `"1. " … "5. "` prefixes sort correctly
  alphabetically, matching severity order)
- Rows: `[Avg Review Score]`
- Color: `[Delay Bucket]` using the 5-color ramp from Section 3.5
- Add data labels showing the value
- Caption: "Review score holds nearly flat from Early (4.30) through Late 1-3 days
  (3.77), then **falls off a cliff** at Late 4-7 days (2.32) and Late 8+ days (1.73) —
  a ~2.5-star swing concentrated in the last two buckets (NB1 Findings #10/#14, NB4
  Finding #32)."

#### Sheet 4.3 — % 1-Star vs. % 5-Star by Delay Bucket

- Data source: `delay_bucket_vs_review.csv`
- Columns: `[Delay Bucket]`
- Rows: two measures via **Measure Names/Measure Values**: `[Pct 1Star]` and
  `[Pct 5Star]`, both format `0.0\%`
- Color: `Measure Names` → `Pct 5Star` = `#55a868`, `Pct 1Star` = `#c44e52`
- Mark: Bar, side-by-side (not stacked) — makes the crossover between the two lines
  visually obvious: 5★ dominates for Early/On-time, 1★ dominates for Late 8+.

#### Sheet 4.4 — Weekly Late-Delivery Rate, Jan–Apr 2018

- Data source: `fulfillment_weekly_2018.csv`
- Columns: `[Week]` (continuous)
- Rows: `[Pct Late]`, Mark: **Line**, color `#4c72b0`, 3px
- **Reference Band**: shade the region where `[Is Anomaly Period]` (calc 4.6) is true
  — in Tableau, add a reference band on the Week axis with a fixed range (the two
  boundary dates from calc 4.6), fill `#c44e52` at 15% opacity, no border
- Dual axis: `[Avg Actual Delivery Days]`, line, color `#8c8c8c`, dashed
- Caption: "Late-delivery rate spikes sharply during the Feb–Mar 2018 window (Carnival-
  period congestion) before reverting — this anomaly is the dominant signal in Model
  A's `purchase_month` feature on Page 7."

#### Sheet 4.5 — Normal vs. Spike Period: State-Level Late Rate

- Data source: `anomaly_state_comparison.csv`
- Columns: `[Customer State]`, sorted descending by `[Pct Late]` where
  `[Period] = "Spike (Feb-Mar 2018)"` — to sort by a specific period's value, use a
  table calc or a secondary sort field; simplest robust approach: create the view
  first with both periods, then use "Sort by field" → `Pct Late` → descending, which
  Tableau applies based on the first/aggregate value per state (verify visually and
  adjust if it sorts oddly with two marks per state).
- Rows: `[Pct Late]`, format `0.0\%`
- Color: `[Period]` → `Normal (Sep-Dec 2017)` = `#55a868`, `Spike (Feb-Mar 2018)` =
  `#c44e52`
- Mark: Bar, side-by-side (two bars per state)
- Filter: limit to states with the largest gap if 24 states is too dense — or keep all
  24 and let users scroll/zoom.
- Caption: "Every state's late rate rises during the Feb-Mar 2018 window — this is a
  systemic operational event, not a regional one."

> **Optional stretch**: a true *dumbbell chart* (two dots connected by a line per
> state, sorted by the gap) is more elegant than side-by-side bars, but requires
> pivoting `period` into columns (via a table calc or a pre-pivoted extract). The
> side-by-side bar above conveys the same finding with far less Tableau complexity —
> recommended for time-boxed builds. If you want the dumbbell: duplicate the `Pct Late`
> pill on Columns, set the second copy's mark type to Line with Path = `Customer
> State`, and use a table calc `WINDOW_MAX` / `WINDOW_MIN` to draw the connector.

#### Dashboard 4 layout

```
┌─────────────────────────────────────────────────────────────────┐
│  Page 4 — Delivery & Fulfillment Operations          [nav row]    │
│  "Where does fulfillment time go, and how does delay drive         │
│   dissatisfaction?"                                                 │
├──────────────────────────┬────────────────────────────────────────┤
│ 4.1 Cycle Time Stages      │  4.2 Delay Bucket vs Review (cliff)     │
│ (funnel bar)               │                                          │
├──────────────────────────┴────────────────────────────────────────┤
│  4.3 %1★ vs %5★ by Delay Bucket (side-by-side bars)                 │
├──────────────────────────┬────────────────────────────────────────┤
│ 4.4 Weekly Late Rate       │  4.5 Normal vs Spike — State Late Rate  │
│ (Jan-Apr 2018, anomaly band)│                                        │
└──────────────────────────┴────────────────────────────────────────┘
```

No cross-filter actions required on this page — it's a diagnostic/narrative page best
read top-to-bottom.

---

### Page 5 — Customer Segmentation

**Business question:** "What distinct customer segments exist, how much revenue does
each drive, and where is the 'At-Risk' segment concentrated?"

**Data sources:** `rfm_segment_summary.csv` (5 rows), `segment_profile_summary.csv`
(4 rows), `customer_segments.csv` (92,746 rows)

#### Sheet 5.1 — RFM Segments: Customers vs. Revenue Share

- Data source: `rfm_segment_summary.csv`
- Columns: `[Rfm Segment]`, sorted descending by `[Pct Revenue]`
- Rows: Measure Names/Values → `[Pct Customers]` and `[Pct Revenue]`, both
  format `0.0\%`
- Color: Measure Names → `Pct Customers` = `#8c8c8c`, `Pct Revenue` = `#4c72b0`
- Mark: Bar, side-by-side
- Tooltip: `[N Customers]`, `[Avg Monetary]`, `[Avg Recency Days]`, `[Pct Repeat]`
- Caption: "Champions = 16.5% of customers but 30.6% of revenue; the bottom two
  segments (Low-Value Lapsed + New/Recent Low-Spend ≈ 32% of customers) generate only
  ~10.7% of revenue combined (NB5 Finding #37)."

#### Sheet 5.2 — Behavioral Segment Profiles (small-multiples grid)

- Data source: `segment_profile_summary.csv` (4 rows: Core High-Value, Loyal Repeat
  Customers, At-Risk: Late & Unhappy, Budget Satisfied)
- Build **6 small bar charts**, each: Columns = `[Segment]`, Rows = one metric below,
  Color = `[Segment]` (palette in Section 3.2). Arrange in a 2×3 or 3×2 grid as small
  multiples — do **not** try to force all metrics onto one shared axis (scales differ
  by 2 orders of magnitude).

| Mini-chart | Metric | Format | Reads as |
|---|---|---|---|
| 1 | `[Recency Days]` | `#,##0.0 "days"` | how recently each segment last purchased |
| 2 | `[Monetary]` | `R$ #,##0.00` | lifetime spend per customer |
| 3 | `[Avg Review Score]` | `0.00` | satisfaction |
| 4 | `[Avg Delivery Delay Days]` | `#,##0.0 "days"` | At-Risk segment should pop here (+9.5 days vs. ~ -13 for others) |
| 5 | `[Pct Late]` | `0.0\%` | At-Risk = 99.7% vs. <6% everywhere else |
| 6 | `[Pct Repeat]` | `0.0\%` | Loyal Repeat = 71.5% vs. <2% everywhere else |

- Caption under the grid: "Each cluster is defined by one extreme, dominant trait —
  Loyal Repeat by `pct_repeat` (71.5%), At-Risk by `avg_delivery_delay_days` (+9.5
  days, the *only* segment with positive average delay) and `pct_late` (99.7%), Core
  High-Value by share of revenue (69.5% from 44.5% of customers). See NB5 Findings
  #38–#40."

#### Sheet 5.3 — PCA Cluster Map

- Data source: `customer_segments.csv` (92,746 rows)
- Columns: `[Pc1]`, Rows: `[Pc2]`
- Mark: **Circle**, size small (~ -1 on the size slider), **opacity 15–25%** (critical
  — 92,746 overlapping points will otherwise render as a solid blob)
- Color: `[Segment]` (palette, Section 3.2)
- Caption: "PC1 + PC2 explain ~46% of variance (27.9% + 18.5%); the 4 segments form
  visually distinct regions in this 2D projection (NB5 Finding #39), and the
  segmentation is highly stable under bootstrap resampling (mean ARI = 0.979, Finding
  #42)."
- **Performance note**: with 92,746 marks this sheet can be slow to render/publish on
  Tableau Public. Mitigations, in order of preference: (1) confirm the extract is
  built (not live) — extracts handle this fine; (2) if still slow, reduce opacity
  further and disable tooltips on hover for this sheet; (3) as a last resort, sample
  to ~20K rows in the extract (not recommended — loses the "full population" framing
  that makes this credible).

#### Sheet 5.4 — At-Risk Segment: Geographic Concentration

- Data source: `customer_segments.csv`
- Filter: `[Segment] = "At-Risk: Late & Unhappy"`
- Columns: `COUNTD([Customer Unique Id])`
- Rows: `[Region]`, sorted descending
- Color: `[Region]` (palette, Section 3.1)
- Add a second, unfiltered reference sheet or a calculated "% of all customers in this
  region" benchmark in the tooltip (computed by comparing against
  `geo_customer_state_summary.csv` totals by region — if building this comparison
  precisely is too fiddly, state the benchmark numbers directly in the caption text
  instead, sourced from NB5 Finding #41).
- Caption: "The At-Risk segment is disproportionately Northeast — this segment exists
  *within every RFM segment* (Finding #40), meaning 'late & unhappy' customers can't
  be found by RFM alone; behavioral clustering is what surfaces them (Finding #41)."

#### Dashboard 5 layout

```
┌─────────────────────────────────────────────────────────────────┐
│  Page 5 — Customer Segmentation                       [nav row]   │
│  "What segments exist, and where is the At-Risk segment           │
│   concentrated?"                                                    │
├──────────────────────────┬────────────────────────────────────────┤
│ 5.1 RFM: Customers vs      │  5.3 PCA Cluster Map                   │
│ Revenue Share               │  (92,746 points, colored by segment)   │
├──────────────────────────┴────────────────────────────────────────┤
│  5.2 Behavioral Segment Profiles — 2x3 small-multiples grid         │
├─────────────────────────────────────────────────────────────────┤
│  5.4 At-Risk Segment — Geographic Concentration by Region           │
└─────────────────────────────────────────────────────────────────┘
```

#### Dashboard actions

- **Filter action**: Source = Sheet 5.2 (segment profile bars — any one of the 6,
  Run on Select), Target = Sheet 5.3 (PCA map) and Sheet 5.4 (At-Risk geography),
  Field `segment` → `segment`. Clicking "At-Risk: Late & Unhappy" on any profile chart
  highlights/filters those 7,319 customers in the PCA scatter and the geography chart.
  - For Sheet 5.4 specifically, since it's pre-filtered to At-Risk only, this action
    would empty it for any other segment — set "Target Filters: Selected Fields" and
    consider making 5.4 a **highlight action** instead of a filter action if you want
    it to stay visible for all segments but highlight on hover.
- **Filter action**: Source = Sheet 5.1 (RFM bars), Target = `customer_segments`-based
  sheets (5.3, 5.4), Field `rfm_segment` → `rfm_segment`.

---

### Page 6 — Seller Marketplace

**Business question:** "How concentrated is the seller base, and which sellers are
high-performing vs. at-risk on delivery/satisfaction?"

**Data sources:** `seller_scorecard.csv` (3,053 sellers), `seller_pareto_deciles.csv`
(10 rows)

#### Sheet 6.1 — Seller Revenue Pareto

- Data source: `seller_pareto_deciles.csv`
- Columns: `[Revenue Decile]` (1 = top 10% of sellers by revenue)
- Rows (dual axis):
  - Bar: `SUM([Decile Revenue])`, color `#4c72b0`, format `R$ #,##0`
  - Line: `SUM([Cumulative Pct Of Revenue])`, color `#c44e52`, right axis 0–100%,
    format `0\%`
- Reference line at 80% on the right axis
- Tooltip: `[N Sellers]`, `[Total Orders]`, `[Pct Of Total Revenue]`
- Caption: "The top 10% of sellers (306 of 3,053) generate 67.5% of marketplace
  revenue — even more concentrated than the demand side (top customer-state
  concentration, Page 3)."

#### Sheet 6.2 — Seller Performance Quadrant

- Data source: `seller_scorecard.csv`
- Columns: `[Pct Late]` (X), format `0.0\%`
- Rows: `[Avg Review Score]` (Y)
- Size: `SUM([Revenue])`
- Color: `[Region]` (palette, Section 3.1, using `seller_state`'s mapped region)
- **Filter**: optionally add `[N Orders] >= 5` to suppress single-order sellers whose
  `pct_late`/`avg_review_score` are 0%/100% or 0%/0% by definition (no variance) —
  use a parameter `Min Orders` (Integer, default 5) so a viewer can adjust.
- Reference lines: average `[Pct Late]` (vertical) and average `[Avg Review Score]`
  (horizontal) → quadrants ("Star Sellers" = low late / high review, top-left)
- Caption: "Bubble size = revenue. Star sellers (top-left) combine reliability with
  satisfaction — candidates for featured-seller programs. Bottom-right sellers combine
  high late-rates with low reviews — candidates for seller-performance interventions."

#### Sheet 6.3 — Top Sellers Table

- Data source: `seller_scorecard.csv`
- Filter: `[Revenue Rank] <= 20`
- Columns (as a text table): `[Seller Id]` (or `LEFT([Seller Id], 8) + "…"`),
  `[Seller State]`, `[N Orders]`, `[Revenue]` (format `R$ #,##0`), `[Avg Review
  Score]`, `[Pct Late]`, `[Revenue Decile]`
- Use **Highlight Table** styling: color `[Pct Late]` cells on a Red ramp and
  `[Avg Review Score]` cells on a Green ramp (two separate color encodings means two
  passes — Tableau text tables support per-measure color via "Measure Names/Values" +
  separate color legends, or build as two overlapping sheets; simplest is a single
  color encoding on `[Pct Late]` with the rest as plain text columns).

#### Sheet 6.4 — Seller Revenue by State

- Data source: `seller_scorecard.csv`
- Columns: `SUM([Revenue])`
- Rows: `[Seller State]`, sorted descending, filter top 10
- Color: `[Region]`

#### Dashboard 6 layout

```
┌─────────────────────────────────────────────────────────────────┐
│  Page 6 — Seller Marketplace                          [nav row]   │
│  "How concentrated is the seller base, and who's high/low          │
│   performing?"                                                      │
├──────────────────────────┬────────────────────────────────────────┤
│ 6.1 Seller Revenue Pareto  │  6.2 Seller Performance Quadrant        │
├──────────────────────────┴────────────────────────────────────────┤
│  6.3 Top 20 Sellers Table              │  6.4 Seller Revenue by State │
└─────────────────────────────────────────────────────────────────┘
```

#### Dashboard actions

- **Filter action**: Source = Sheet 6.1 (Pareto deciles), Target = Sheet 6.3 (Top
  Sellers table) and Sheet 6.2 (Quadrant), Field `revenue_decile` → `revenue_decile`.
  Clicking decile 1 isolates the top-306-seller cohort everywhere on the page.

---

### Page 7 — Predictive Risk Scoring

**Business question:** "Which orders are most likely to be late or to generate a
negative review, what drives those predictions, and where do they concentrate?"

**Data sources:** `risk_scores_late_delivery.csv` (94,726 orders, Model A),
`feature_importance_model_a.csv` (11 rows), `risk_scores_negative_review.csv`
(95,824 orders, Model B), `feature_importance_model_b.csv` (11 rows)

> **Modeling context** (for the caption text on this page): both models are
> `RandomForestClassifier(n_estimators=200, max_depth=8, class_weight="balanced")`,
> retrained on the **full population** for these dashboard scores (held-out
> validation metrics: Model A AUC=0.742 / PR-AUC=0.215; Model B AUC≈0.745 /
> PR-AUC≈0.270 — NB6 Finding #44). `risk_decile` = 1 is the **highest-risk** decile
> (deciles 1–2 = "High Risk (top 20%)", 3–5 = "Medium Risk (next 30%)", 6–10 = "Low
> Risk (bottom 50%)" — see `risk_tier`).

#### Sheet 7.1 — Model A: Late-Delivery Risk — Decile Lift Chart

- Data source: `risk_scores_late_delivery.csv`
- Columns: `[Risk Decile]` (discrete, 1→10 left to right)
- Rows: `[Late Rate]` (calc 4.7, format Percentage)
- Color: `[Risk Tier]` (palette, Section 3.4)
- **Reference line**: constant at 8.11% (the overall `pct_late_overall` from
  `kpi_summary`), label "Overall avg: 8.1%"
- Caption: "Decile 1 (highest predicted risk) has a late rate roughly 3x the overall
  average. Flagging the riskiest 10% of orders at order-time catches ~30% of all
  late deliveries (NB6 Finding #46) — actionable for proactive customer communication
  or carrier reassignment."

#### Sheet 7.2 — Model A: Feature Importance

- Data source: `feature_importance_model_a.csv`
- Rows: `[Feature Label]` (calc 4.9), sorted by `[Rank]` ascending (so rank 1 is at
  top — in Tableau, sort descending on `-[Rank]` or manually reverse the axis)
- Columns: `[Pct Of Total Importance]`, format `0.0\%`
- Mark: Bar, single color `#4c72b0` (or a gradient by importance)
- Data labels: show `[Pct Of Total Importance]` at bar end

> **⚠ Required caption — read before building this sheet.** This grouped feature
> importance ranks **`Purchase Month` #1 at 52.6%**, ahead of `Estimated Delivery
> Window (days)` (19.7%, #2) and `Customer-Seller Distance (km)` (13.2%, #3). At first
> glance this looks like it *contradicts* NB6 Finding #44, which calls
> `estimated_delivery_days` and `distance_km` the top predictors. **It doesn't** — the
> two rankings answer different questions:
> - NB6 Finding #44 ranks **individual, ungrouped** model features (one-hot dummy
>   columns are counted separately, e.g. `purchase_month_3` is its own feature there).
> - This dashboard's `feature_importance_model_a.csv` is a **grouped** importance —
>   all 12 one-hot dummies for `purchase_month` (Jan…Dec) are summed back into one
>   `purchase_month` row.
> - The grouped total is dominated by a **single month**: `purchase_month_3` (March)
>   alone carries raw importance 0.170 — i.e. almost the entire `purchase_month`
>   group's weight comes from one month, not from "month" being generically
>   predictive across the year.
> - **March is the Feb–Mar 2018 fulfillment-crisis month** (Page 4, Sheet 4.4;
>   Carnival-period congestion). The model has essentially learned "if this order was
>   placed in March [2018], it was much more likely to be late" — which is a real,
>   correctly-learned signal from one anomalous period in the training data, not
>   evidence that delivery-window/distance are unimportant.
>
> **Caption text to place under Sheet 7.2:**
> *"`Purchase Month` ranks #1 here because one month — March — was the epicenter of
> the Feb-Mar 2018 fulfillment anomaly (see Page 4); summed across the other 11
> months it contributes far less. Per-feature (ungrouped) importance ranks
> `estimated_delivery_days` and `distance_km` highest (NB6 Finding #44) — both views
> are correct; this one shows which **business dimension** matters most, the other
> shows which **individual signal** matters most."*

#### Sheet 7.3 — Model B: Negative-Review Risk — Decile Lift Chart

- Data source: `risk_scores_negative_review.csv`
- Columns: `[Risk Decile]`
- Rows: `[Negative Review Rate]` (calc 4.8, format Percentage)
- Color: `[Risk Tier]` (palette, Section 3.4)
- Reference line at 13.77% (`pct_negative_review_overall` from `kpi_summary`)
- Caption: "Decile 1 has a 53.7% negative-review rate vs. 13.8% overall — a 4.2x lift
  (NB6 Finding #49). Because Model B's top features are `is_late` and
  `delivery_delay_days` (Sheet 7.4), and Model A's order-time risk score still
  predicts Model B's outcome (Finding #50), a **high Model-A score at order time is
  itself an early warning for Model B's outcome** — i.e., delivery risk and
  satisfaction risk are the same underlying problem viewed at two points in the order
  lifecycle."

#### Sheet 7.4 — Model B: Feature Importance

- Data source: `feature_importance_model_b.csv`
- Same structure as Sheet 7.2
- Caption: "`Delivery Delay (days)` (39.4%) + `Order Was Late` (32.5%) = 71.8% of
  total importance — delivery experience overwhelmingly drives review sentiment
  (NB6 Finding #47). `Items per Order` (12.2%) is a distant third — basket complexity
  matters, but only after delivery performance (Finding #48)."

#### Sheet 7.5 — Geographic Risk Map

- Data source: `risk_scores_late_delivery.csv`
- Detail: `[State Name]`, `[Country]` (calc 4.7's data source also needs its own
  `Country = "Brazil"` calc, listed in 4.7)
- Color: `AVG([Predicted Late Risk])`, built-in Percentage format, sequential
  Orange-Red ramp
- Caption: "Average model-predicted late-delivery risk by customer state — compare
  against the *actual* late-rate map on Page 3 (Sheet 3.1b) to see how well the
  model's predictions track observed outcomes geographically."

#### Sheet 7.6 — Order-Level Risk Explorer

- Data source: `risk_scores_late_delivery.csv`
- Columns: `[Estimated Delivery Days]`
- Rows: `[Distance Km]`
- Color: `[Risk Tier]` (palette, Section 3.4)
- Size: `[Order Total Value]`
- Filters (shown as dashboard filter widgets, "Apply to worksheets: This worksheet"):
  `[Category Grp]` (multi-select dropdown), `[Customer Region]` (multi-select), and
  `[Risk Tier]` (multi-select)
- This is the "drill into individual orders" sheet — lets a viewer (e.g., an ops
  analyst) explore *which* orders the model flags as high-risk and inspect their
  characteristics.

#### Dashboard 7 layout

```
┌─────────────────────────────────────────────────────────────────┐
│  Page 7 — Predictive Risk Scoring                     [nav row]   │
│  "Which orders are at risk, what drives the prediction, and        │
│   where does risk concentrate?"                                     │
├──────────────────────────┬────────────────────────────────────────┤
│ 7.1 Model A Decile Lift    │  7.3 Model B Decile Lift                │
├──────────────────────────┼────────────────────────────────────────┤
│ 7.2 Model A Feature        │  7.4 Model B Feature Importance         │
│ Importance + ⚠ caption     │                                          │
├──────────────────────────┴────────────────────────────────────────┤
│  7.5 Geographic Risk Map    │  7.6 Order-Level Risk Explorer          │
│  (Model A predicted risk)   │  (filterable scatter)                   │
└─────────────────────────────────────────────────────────────────┘
```

#### Dashboard actions

- **Filter action**: Source = Sheet 7.1 (Model A decile lift), Target = Sheet 7.6
  (Order Explorer), Field `risk_decile` → `risk_decile`. Clicking decile 1 filters the
  explorer to only the riskiest orders.
- Standard dashboard **filter widgets** for `category_grp`, `customer_region`,
  `risk_tier` (described in Sheet 7.6) — set "Apply to: Selected Worksheets" → Sheet
  7.6 only, so the filters don't unexpectedly affect the decile charts' overall
  averages.

---

## 6. Cross-page navigation

After all 7 dashboards are built:

1. On Dashboard 1, add a horizontal **Layout Container** in the top-right corner.
2. Add 7 **Navigation objects** (Dashboard → Navigation), one per page, each showing
   a short label ("1 Overview", "2 Sales", "3 Geography", "4 Delivery", "5 Segments",
   "6 Sellers", "7 Risk") and a thumbnail/blank image, target = the corresponding
   dashboard.
3. Copy this container (Ctrl/Cmd+C) and paste it onto each of the other 6 dashboards
   so the nav bar is identical everywhere — then on each dashboard, edit that page's
   own button to look "active" (e.g., bold border or different fill) so users always
   know where they are.

---

## 7. Publishing checklist (Tableau Public)

1. For every data source: **Data → [source] → Extract → Compute Now**, then verify
   row counts match the table in `etl/export_dashboard_extracts.py`'s trailing
   "EXTRACT CATALOG" comment.
2. Verify every `pct_*` field shows a `%` sign with the correct magnitude (spot-check
   `kpi_summary.pct_late_overall` should render "8.1%", not "811.0%" or "0.1%") —
   Section 0.1.
3. Verify all 4 geo-enabled sources show **0 unknown/unmatched** states on their maps
   (Tableau flags ungeocoded values with a small warning icon on the map sheet — click
   it to confirm "0 unrecognized").
4. Click through every filter/highlight action on every page to confirm it fires and
   that a "clear selection" returns the view to its default state.
5. **File → Save to Tableau Public As…** — choose a clear workbook name (e.g.,
   "Olist E-Commerce Analytics — Data Analyst Portfolio").
6. After publishing, open the public URL in a private/incognito window to confirm it
   renders correctly for an unauthenticated viewer (maps, filters, and tooltips all
   load).
7. Add the published URL to `README.md` and `docs/CASE_STUDY.md` once those are
   written.

---

## 8. Findings index (cross-referenced to dashboard pages)

For traceability between the notebooks (source of truth for every number) and the
dashboard (the presentation layer). NB1–NB4 findings are numbered #1–#36; NB5 = #37–43;
NB6 = #44–50.

| # | Finding (short) | Notebook | Dashboard page |
|---|---|---|---|
| 1 | Star schema fully reconciled, no imputation needed | NB1 | — (data quality, `docs/data_quality_report.md`) |
| 2 | 97.02% of orders reach `delivered` | NB1 | Page 1 (implicit in KPI base) |
| 3 | Demand concentrated: SP=42% of orders, top 4 states >70% | NB1 | Page 3 |
| 4 | Monetary vars extremely right-skewed — log1p needed | NB1 | (modeling input, Page 7) |
| 5 | `review_score` J-shaped, 59.9% 5★ / 11.7% 1★ | NB1 | Page 4 (Sheet 4.3) |
| 6 | Median delivery delay = -11.9 days (early) | NB1 | Page 4 |
| 7 | Highest-value order ($13,664) is legit bulk purchase, 1★ | NB1 | — |
| 8 | 775 zero-item orders, $0 GMV, no distortion | NB1 | — |
| 9 | Price↔freight r≈0.41–0.43, weight/distance-driven | NB1 | — |
| 10 | Delay→review correlation non-linear ("cliff") | NB1 | Page 4 (Sheet 4.2) |
| 11 | Installments proxy basket size ($119→$355) | NB1 | — |
| 12 | Review correlates more with delivery timing than price | NB1 | — |
| 13 | Longer SLA windows are padded more generously (r=-0.51) | NB1 | — |
| 14 | Late orders → systematically lower reviews | NB1, NB4 | Page 4 |
| 15 | Monday peak / Saturday trough order-day seasonality | NB2 | — |
| 16 | Jun–Aug 2018 "decline" is a right-censoring artifact | NB2 | — |
| 17 | Triangulated Aug-2018 GMV likely understated | NB2 | — |
| 18 | Nov-2017 +64% spike confirmed by STL decomposition | NB2 | Page 1 (Sheet 1.5) |
| 19 | Daily orders non-stationary in levels, stationary after diff | NB2 | — |
| 20 | Mature-period growth ≈ R$45,955/month (R²=0.673) | NB2 | Page 1 (Sheet 1.2) |
| 21 | Jun-2018 dip coincides with World Cup (unverified) | NB2 | — |
| 22 | Holt-Winters Sep–Nov 2018 forecast ~R$1.0–1.05M | NB2 | — |
| 23 | SP=37.4% GMV/41.8% customers; top 5 states=73.1% | NB3 | Page 3 (Sheet 3.1a, 3.4) |
| 24 | `pct_late` varies 8x by state (2.9% RO → 23.9% AL) | NB3 | Page 3 (Sheet 3.1b) |
| 25 | SLA buffer thinness predicts `pct_late` (r=0.72) | NB3 | — |
| 26 | `avg_review_score` ↔ `pct_late` r=-0.79 | NB3 | Page 3 (Sheet 3.1c) |
| 27 | Distance-decay monotonic across 8 buckets | NB3 | — |
| 28 | 64% of single-seller orders are cross-state | NB3 | Page 3 (Sheet 3.3) |
| 29 | Seller supply more concentrated than demand (SP=64.6%) | NB3 | Page 3 (Sheet 3.2), Page 6 |
| 30 | City-level concentration sharper than state-level | NB3 | — |
| 31 | `is_late` strongest review predictor (Cliff's delta=-0.554) | NB4 | Page 4 |
| 32 | All 10 delay-bucket pairwise comparisons significant | NB4 | Page 4 (Sheet 4.2) |
| 33 | 16/53 categories differ significantly from grand-mean review | NB4 | Page 2 (Sheet 2.2) |
| 34 | Region effect on review/delay "negligible-to-small" | NB4 | — |
| 35 | Payment type predicts order value, not review score | NB4 | — |
| 36 | Distance predicts delivery time/freight, weakly predicts delay | NB4 | — |
| 37 | RFM recap — 5 segments, revenue concentration | NB5 | Page 5 (Sheet 5.1) |
| 38 | k=4 chosen for K-Means | NB5 | Page 5 (Sheet 5.2/5.3) |
| 39 | PC1+PC2 ~46% variance, 4 clean clusters | NB5 | Page 5 (Sheet 5.3) |
| 40 | At-Risk customers hide inside every RFM segment | NB5 | Page 5 |
| 41 | At-Risk disproportionately Northeast | NB5 | Page 5 (Sheet 5.4) |
| 42 | Segmentation stable (bootstrap ARI=0.979) | NB5 | Page 5 (Sheet 5.3 caption) |
| 44 | Model A AUC=0.742/PR-AUC=0.215; top predictors = delivery window, distance | NB6 | Page 7 (Sheet 7.1, 7.2 caption) |
| 45 | Purchase month is the largest grouped predictor (Mar 2018 anomaly) | NB6 | Page 7 (Sheet 7.2) |
| 46 | Top risk decile catches ~30% of late orders | NB6 | Page 7 (Sheet 7.1) |
| 47 | Model B: delay & lateness dominate (71.8% combined) | NB6 | Page 7 (Sheet 7.4) |
| 48 | Basket composition matters after delivery performance | NB6 | Page 7 (Sheet 7.4) |
| 49 | Model B decile 1 = 53.7% negative-review rate (4.2x lift) | NB6 | Page 7 (Sheet 7.3) |
| 50 | Model A's order-time score predicts Model B's outcome | NB6 | Page 7 (Sheet 7.3 caption) |

*(Finding #43 — bootstrap stability detail folded into #42's narrative; no separate
dashboard element.)*
