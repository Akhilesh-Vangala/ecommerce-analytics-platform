"""Generator for notebooks/04_hypothesis_testing.ipynb.

Edit this file, then regenerate with:
    .venv/bin/python notebooks/_build_nb04.py
    .venv/bin/jupyter nbconvert --to notebook --execute --inplace \
        notebooks/04_hypothesis_testing.ipynb --ExecutePreprocessor.timeout=600
"""
import nbformat as nbf

nb = nbf.v4.new_notebook()
cells = []

def md(src):
    cells.append(nbf.v4.new_markdown_cell(src))

def code(src):
    cells.append(nbf.v4.new_code_cell(src))


# ============================================================================
# Title & roadmap
# ============================================================================
md(r"""# Notebook 4 — Formal Hypothesis Testing: Delivery, Reviews, Categories, Regions & Payments

**Project:** E-Commerce Retail & Fulfillment Analytics — an Amazon Retail / Operations analog
built on the Olist Brazilian e-commerce dataset (Sep-2016 – Oct-2018).

## Where this fits in the project

Notebooks 1-3 established a consistent descriptive narrative: late deliveries correlate with
sharply lower review scores (NB1 F14, Pearson r=-0.267, Spearman r=-0.176 — a non-linear
"cliff" rather than a straight line); some product categories and Brazilian regions look
systematically better or worse on review score and on-time rate (NB1 Sections 6-7, NB3
F24-F26); and `pct_late` itself is driven less by absolute distance/delivery time than by how
"thin" each state's SLA buffer is (NB3 F25, r=0.72).

**Every one of those is a correlation or a group-mean difference computed on the full
~96K-order sample.** At this sample size, *any* non-zero difference produces a tiny p-value —
so "statistically significant" is close to meaningless on its own. This notebook does the
senior-analyst version of that work: for each relationship, it (a) states a formal
null/alternative hypothesis, (b) picks a test appropriate to the data's actual distribution
(verified, not assumed), (c) reports an **effect size** alongside the p-value, and (d)
corrects for **multiple comparisons** wherever more than one pairwise test is run from the
same data. The output is a ranked answer to the question a hiring manager actually cares
about: *of all the things that "correlate" with review score, which ones actually move the
needle, and by how much?*

## Why non-parametric tests dominate this notebook

`review_score` is a **5-point ordinal/discrete** variable with the J-shaped distribution
documented in NB1 Section 3 (59.2% 5-star, but 11.7% 1-star — not remotely Normal), and
`delivery_delay_days` / `order_total_value` are heavily right-skewed (NB1 Section 4). Treating
either as Normal and running a t-test/ANOVA/Pearson correlation would violate the test's core
assumption and risks both false positives and understated effect sizes for the "cliff"-shaped
relationships NB1 already flagged. Throughout this notebook we therefore default to:

| Comparison | Parametric (not used) | Non-parametric (used here) | Effect size reported |
|---|---|---|---|
| 2 independent groups | Welch's t-test | **Mann-Whitney U** | Cliff's delta |
| k independent groups | One-way ANOVA | **Kruskal-Wallis H** | epsilon-squared (ε²) |
| 2 categorical variables | — | **Chi-square test of independence** | Cramér's V |
| 2 continuous/ordinal variables | Pearson r | **Spearman ρ** (+ bootstrap 95% CI) | ρ itself |

Every post-hoc pairwise test (after a significant Kruskal-Wallis) is corrected with the
**Holm-Bonferroni** procedure (`statsmodels.stats.multitest.multipletests`, `method="holm"`)
— more powerful than a flat Bonferroni correction while still controlling the family-wise
error rate.

## Hypotheses tested in this notebook

| # | Section | Hypothesis (H1) | Motivated by |
|---|---|---|---|
| H1 | 1 | Orders delivered **late** receive systematically lower review scores than on-time orders | NB1 F14 |
| H2 | 2 | Review-score distributions differ across the 5 delivery-delay buckets, including between adjacent "early" and "on-time" buckets | NB1 Section 7 |
| H3 | 3 | Average review score varies significantly by **product category**, independent of each category's delivery performance | NB1 Section 6 |
| H4 | 4 | The 5 IBGE macro-regions differ significantly in both review score and delivery delay | NB3 F24-F26 |
| H5 | 5 | Payment method and installment count relate to order value and (separately) to review score | New |
| H6 | 6 | Haversine distance is significantly correlated with delivery time and freight cost, but only weakly with delivery *delay* | NB3 F27 |

| # | Notebook | Focus |
|---|---|---|
| 1 | `01_data_profiling_and_eda.ipynb` | Profiling, missingness, univariate/bivariate/multivariate EDA |
| 2 | `02_time_series_decomposition.ipynb` | Trend/seasonality decomposition of orders & revenue |
| 3 | `03_geospatial_analysis.ipynb` | State/city geography — demand, delivery, satisfaction, supply-vs-demand |
| 4 | `04_hypothesis_testing.ipynb` (this notebook) | Formal statistical tests — delivery delay vs. review score, category/region effects |
| 5 | `05_customer_segmentation.ipynb` | RFM + K-means clustering, segment profiles |
| 6 | `06_predictive_modeling.ipynb` | Logistic regression — late-delivery & low-review risk |""")


# ============================================================================
# Setup
# ============================================================================
code(r'''import sys
from pathlib import Path

sys.path.insert(0, str(Path.cwd().parent))

import numpy as np
import pandas as pd
import matplotlib.pyplot as plt
import seaborn as sns
from scipy import stats
from statsmodels.stats.multitest import multipletests

from etl.db import get_engine

%matplotlib inline
sns.set_theme(style="whitegrid", context="notebook", palette="deep")
plt.rcParams["figure.dpi"] = 110
plt.rcParams["figure.facecolor"] = "white"
plt.rcParams["axes.titleweight"] = "bold"

pd.set_option("display.max_columns", 60)
pd.set_option("display.float_format", lambda v: f"{v:,.4f}")

engine = get_engine()
print("Connected to:", engine.url.render_as_string(hide_password=True))

REGION_ORDER = ["North", "Northeast", "Central-West", "Southeast", "South"]
REGION_COLORS = dict(zip(REGION_ORDER, sns.color_palette("deep", len(REGION_ORDER)).as_hex()))
BR_REGION = {
    "AC": "North", "AP": "North", "AM": "North", "PA": "North", "RO": "North", "RR": "North", "TO": "North",
    "AL": "Northeast", "BA": "Northeast", "CE": "Northeast", "MA": "Northeast", "PB": "Northeast",
    "PE": "Northeast", "PI": "Northeast", "RN": "Northeast", "SE": "Northeast",
    "DF": "Central-West", "GO": "Central-West", "MS": "Central-West", "MT": "Central-West",
    "ES": "Southeast", "MG": "Southeast", "RJ": "Southeast", "SP": "Southeast",
    "PR": "South", "RS": "South", "SC": "South",
}

# ---------------------------------------------------------------------------
# Statistical-testing helper functions used throughout this notebook
# ---------------------------------------------------------------------------
def cliffs_delta(x, y):
    """Cliff's delta = P(X>Y) - P(X<Y), derived from the Mann-Whitney U statistic."""
    n1, n2 = len(x), len(y)
    U, _ = stats.mannwhitneyu(x, y, alternative="two-sided")
    return 2 * U / (n1 * n2) - 1

def interpret_cliffs_delta(d):
    ad = abs(d)
    if ad < 0.147: return "negligible"
    if ad < 0.33:  return "small"
    if ad < 0.474: return "medium"
    return "large"

def cramers_v(table):
    """Cramer's V + the underlying chi-square test of independence."""
    chi2, p, dof, _ = stats.chi2_contingency(table)
    n = table.to_numpy().sum()
    r, k = table.shape
    v = np.sqrt((chi2 / n) / (min(r - 1, k - 1)))
    return v, chi2, p, dof

def interpret_v(v):
    if v < 0.1: return "negligible"
    if v < 0.3: return "small"
    if v < 0.5: return "medium"
    return "large"

def epsilon_sq(H, n):
    """Epsilon-squared effect size for a Kruskal-Wallis H statistic (Tomczak & Tomczak 2014)."""
    return H / (n - 1)

def interpret_eps2(e):
    if e < 0.01: return "negligible"
    if e < 0.06: return "small"
    if e < 0.14: return "medium"
    return "large"

def holm(pvals):
    reject, p_adj, _, _ = multipletests(pvals, alpha=0.05, method="holm")
    return reject, p_adj

def bootstrap_ci_spearman(x, y, n_boot=1000, seed=42):
    rng = np.random.default_rng(seed)
    n = len(x)
    x, y = np.asarray(x), np.asarray(y)
    corrs = np.empty(n_boot)
    for i in range(n_boot):
        idx = rng.integers(0, n, n)
        corrs[i] = stats.spearmanr(x[idx], y[idx])[0]
    return np.percentile(corrs, [2.5, 97.5])

print("Helper functions defined: cliffs_delta, cramers_v, epsilon_sq, holm, bootstrap_ci_spearman")''')

md(r"""### Core analysis dataset

All sections share one base extract: every **delivered, reviewed order** from
`marts.fact_orders` (n=95,824 — 97.0% of delivered orders have a review, consistent with
NB1's missingness profile). We attach the `region` (IBGE macro-region, via `BR_REGION`), the
3-level `review_cat` (negative/neutral/positive), and the 5-level `delay_bucket` (identical
bin edges to NB1 Section 7) used throughout this notebook.""")

code(r'''orders = pd.read_sql("""
    SELECT
        order_id, customer_state, order_total_value, freight_value_total,
        review_score, delivery_delay_days, actual_delivery_days,
        estimated_delivery_days, is_late, primary_payment_type, max_installments, n_items
    FROM marts.fact_orders
    WHERE is_delivered AND review_score IS NOT NULL AND delivery_delay_days IS NOT NULL
""", engine)

orders["region"] = orders["customer_state"].map(BR_REGION)
orders["review_cat"] = pd.cut(orders["review_score"], bins=[0, 2, 3, 5],
                               labels=["1-2 (negative)", "3 (neutral)", "4-5 (positive)"])
orders["delay_bucket"] = pd.cut(
    orders["delivery_delay_days"],
    bins=[-np.inf, -2, 0, 3, 7, np.inf],
    labels=["1. Early (2+ d)", "2. On-time (0-1d ahead)", "3. Late 1-3d", "4. Late 4-7d", "5. Late 8+d"]
)

print(f"orders: {len(orders):,} delivered, reviewed orders")
print((100 * orders["review_score"].value_counts(normalize=True).sort_index()).round(1).rename("pct"))
print(f"\npct_late = {100*orders['is_late'].mean():.2f}%")''')


# ============================================================================
# Section 1: Late vs On-time -> review_score (H1)
# ============================================================================
md(r"""## 1. Late vs. On-Time Delivery → Review Score (H1)

**H0:** the distribution of `review_score` is the same for orders delivered late
(`is_late = True`) and on-time (`is_late = False`).
**H1:** late orders have a systematically lower `review_score` distribution.

`review_score` is ordinal (1-5) and heavily skewed (J-shaped, NB1 Section 3), so we test H1
with a one-sided **Mann-Whitney U test** (`alternative="less"`) and report **Cliff's delta**
as the effect size. We also run the equivalent **Kruskal-Wallis** (2-group KW ≡ Mann-Whitney)
to get an **epsilon-squared** directly comparable to Sections 2-4. Finally, we collapse
`review_score` into `review_cat` and run a **chi-square test of independence** against
`is_late`, reporting **Cramér's V**.""")

code(r"""late = orders.loc[orders["is_late"], "review_score"]
ontime = orders.loc[~orders["is_late"], "review_score"]

print(f"n_late={len(late):,} ({100*len(late)/len(orders):.2f}%), n_ontime={len(ontime):,}")
print(f"mean review_score | late   = {late.mean():.3f}")
print(f"mean review_score | ontime = {ontime.mean():.3f}")

U, p = stats.mannwhitneyu(late, ontime, alternative="less")
delta_h1 = cliffs_delta(late, ontime)
print(f"\nMann-Whitney U (H1: late < on-time, one-sided): U={U:,.0f}, p={p:.2e}")
print(f"Cliff's delta = {delta_h1:.3f} ({interpret_cliffs_delta(delta_h1)})")

H_islate, p_islate = stats.kruskal(late, ontime)
eps2_islate = epsilon_sq(H_islate, len(orders))
print(f"\nEquivalent 2-group Kruskal-Wallis: H={H_islate:,.1f}, p={p_islate:.2e}, "
      f"epsilon^2={eps2_islate:.4f} ({interpret_eps2(eps2_islate)})")

ct1 = pd.crosstab(orders["is_late"], orders["review_cat"])
v1, chi2_1, pchi_1, dof1 = cramers_v(ct1)
print(f"\nChi-square (is_late x review_cat): chi2={chi2_1:,.1f}, dof={dof1}, p={pchi_1:.2e}")
print(f"Cramer's V = {v1:.3f} ({interpret_v(v1)})")
print("\nRow percentages:")
print((100 * ct1.div(ct1.sum(axis=1), axis=0)).round(1))""")

code(r"""fig, axes = plt.subplots(1, 2, figsize=(12, 4.5))

pct = (100 * ct1.div(ct1.sum(axis=1), axis=0))[["1-2 (negative)", "3 (neutral)", "4-5 (positive)"]]
pct.index = ["On-time", "Late"]
colors = ["#c0392b", "#95a5a6", "#27ae60"]
pct.plot(kind="bar", stacked=True, ax=axes[0], color=colors, width=0.55)
axes[0].set_ylabel("% of orders")
axes[0].set_xlabel("")
axes[0].set_title("Review-score mix: on-time vs. late")
axes[0].legend(title="Review category", bbox_to_anchor=(1.02, 1), loc="upper left")
axes[0].set_ylim(0, 100)
axes[0].tick_params(axis="x", rotation=0)
for i, row in enumerate(pct.values):
    cum = 0
    for v in row:
        if v > 3:
            axes[0].text(i, cum + v/2, f"{v:.0f}%", ha="center", va="center",
                          color="white", fontsize=10, fontweight="bold")
        cum += v

plot_df = orders.assign(group=np.where(orders["is_late"], "Late", "On-time"))
sns.violinplot(data=plot_df, x="group", y="review_score", ax=axes[1],
               order=["On-time", "Late"], hue="group",
               palette={"On-time": "#3498db", "Late": "#e74c3c"}, legend=False,
               cut=0, inner="quartile")
axes[1].set_title("review_score distribution: on-time vs. late")
axes[1].set_xlabel("")

plt.tight_layout()
plt.show()""")

md(r"""### Finding: late delivery is overwhelmingly the strongest single predictor of a bad review

H1 is confirmed with overwhelming significance (Mann-Whitney p≈0 at n=95,824) and a **large**
effect size by Cliff's delta (-0.554, above the 0.474 "large" threshold) — a **medium**
effect size by epsilon² (0.086, just short of the 0.14 "large" threshold). Average review
score drops from **4.29 (on-time) to 2.57 (late)** — a 1.7-star
swing on a 5-point scale. The chi-square test on the 3-level `review_cat` is equally decisive
(Cramér's V = 0.372, "medium-large"): only **34.6% of late orders are rated 4-5 stars**,
versus **82.8% of on-time orders** — and **54.1% of late orders are rated 1-2 stars**, versus
just 9.2% of on-time orders. This single binary flag — `is_late` — is one of the two
strongest review-score signals tested anywhere in this notebook (full ranking in Section 7).""")


# ============================================================================
# Section 2: Delay buckets -> review_score (H2, Kruskal-Wallis + post-hoc)
# ============================================================================
md(r"""## 2. Delivery-Delay Buckets → Review Score (H2)

Section 1 collapsed delivery performance into a binary `is_late` flag. NB1 Section 7 used a
finer 5-level `delay_bucket` (reused here, identical bin edges):

| Bucket | `delivery_delay_days` range |
|---|---|
| 1. Early (2+ d) | < -2 (delivered 2+ days ahead of estimate) |
| 2. On-time (0-1d ahead) | -2 to 0 |
| 3. Late 1-3d | 0 to 3 |
| 4. Late 4-7d | 3 to 7 |
| 5. Late 8+d | > 7 |

**H0:** `review_score` has the same distribution across all 5 `delay_bucket` levels.
**H1:** at least one bucket's distribution differs.

We test with a **Kruskal-Wallis H test**, report **epsilon-squared**, and — since H0 is
all but certain to be rejected at this sample size — run all **C(5,2)=10 pairwise
Mann-Whitney tests** with **Holm-Bonferroni correction**, since the natural follow-up
question is: *which specific buckets actually differ from each other?*""")

code(r"""groups = [g["review_score"].values for _, g in orders.groupby("delay_bucket", observed=True)]
bucket_labels = [k for k, _ in orders.groupby("delay_bucket", observed=True)]
n_per_bucket = orders["delay_bucket"].value_counts().sort_index()

H, p = stats.kruskal(*groups)
eps2 = epsilon_sq(H, len(orders))
print(f"Kruskal-Wallis H = {H:,.1f}, p = {p:.2e}, epsilon^2 = {eps2:.4f} ({interpret_eps2(eps2)})")

summary2 = pd.DataFrame({
    "n_orders": n_per_bucket,
    "mean_review_score": orders.groupby("delay_bucket", observed=True)["review_score"].mean(),
    "pct_5star": 100*orders.groupby("delay_bucket", observed=True)["review_score"].apply(lambda s: (s == 5).mean()),
    "pct_1star": 100*orders.groupby("delay_bucket", observed=True)["review_score"].apply(lambda s: (s == 1).mean()),
})
summary2""")

code(r"""pairs2, pvals2 = [], []
for i in range(len(bucket_labels)):
    for j in range(i + 1, len(bucket_labels)):
        _, pv = stats.mannwhitneyu(groups[i], groups[j], alternative="two-sided")
        pairs2.append((bucket_labels[i], bucket_labels[j]))
        pvals2.append(pv)
reject2, p_holm2 = holm(pvals2)
posthoc2 = pd.DataFrame({
    "bucket_1": [a for a, b in pairs2], "bucket_2": [b for a, b in pairs2],
    "p_raw": pvals2, "p_holm": p_holm2, "significant (alpha=0.05)": reject2,
})
print(f"{reject2.sum()} of {len(reject2)} pairwise comparisons significant after Holm correction")
posthoc2""")

code(r"""fig, axes = plt.subplots(1, 2, figsize=(13, 5))

short_labels = ["Early\n(2+d)", "On-time\n(0-1d)", "Late\n1-3d", "Late\n4-7d", "Late\n8+d"]
sns.violinplot(data=orders, x="delay_bucket", y="review_score", ax=axes[0],
               order=bucket_labels, hue="delay_bucket", palette="RdYlGn_r", legend=False,
               cut=0, inner="quartile")
axes[0].set_xticks(range(len(short_labels)))
axes[0].set_xticklabels(short_labels)
axes[0].set_xlabel("")
axes[0].set_title(f"review_score by delay bucket\n(KW H={H:,.0f}, p<0.001, ε²={eps2:.3f})")

mat = pd.DataFrame(np.nan, index=bucket_labels, columns=bucket_labels)
for (a, b), p_adj in zip(pairs2, p_holm2):
    val = -np.log10(max(p_adj, 1e-300))
    mat.loc[a, b] = val
    mat.loc[b, a] = val
sns.heatmap(mat, annot=True, fmt=".0f", cmap="Reds", ax=axes[1], cbar_kws={"label": "-log10(p_holm)"},
            xticklabels=short_labels, yticklabels=short_labels, linewidths=0.5, linecolor="white")
axes[1].set_title("Post-hoc pairwise significance\n(-log10 p, Holm-corrected — all 10 pairs significant)")

plt.tight_layout()
plt.show()""")

md(r"""### Finding: every delay-bucket pair is significantly different — even "Early" vs. "On-time"

The Kruskal-Wallis test rejects H0 overwhelmingly (H=10,189.6, p≈0) with **epsilon²=0.106
("medium", just short of the 0.14 "large" threshold)** — the single largest effect size of any factor tested in this notebook (Section
7 leaderboard). Mean review score falls in a near-monotonic staircase from **4.30 (Early) →
4.14 (On-time) → 3.77 (Late 1-3d) → 2.32 (Late 4-7d) → 1.73 (Late 8+d)**.

The post-hoc table shows **all 10 of 10 pairwise comparisons remain significant after
Holm-Bonferroni correction** — including Early vs. On-time (p_holm = 5.0e-17), the smallest
gap (4.30 vs 4.14, only 0.16 stars). With n=85,173 vs n=2,990 in those two buckets, even a
0.16-star difference is easily detectable. The practical reading: **review score responds
continuously to how much "buffer" an order arrives with, not just a binary late/on-time
cutoff** — every additional day of buffer (or of lateness) measurably moves satisfaction,
reinforcing NB3 F25's "buffer thinness" framing as the operationally controllable lever.""")


# ============================================================================
# Section 3: Product category effects (H3)
# ============================================================================
md(r"""## 3. Product-Category Effects on Review Score (H3)

NB1 Section 6 showed category-level differences in price/freight; here we test whether
`review_score` itself differs by `product_category_name_english` (joined via
`marts.fact_order_items` → `marts.dim_product`), restricted to the 53 categories with ≥100
reviewed orders (of 74 total categories).

**H0:** `review_score` has the same distribution across all 53 categories.
**H1:** at least one category differs.

We run the omnibus **Kruskal-Wallis** test first, then — because 53 categories produce
C(53,2)=1,378 pairs (too many for a meaningful pairwise table) — a more interpretable
**one-vs-rest** design: for each category, a two-sided Mann-Whitney test of that category's
`review_score` against *every other category combined*, with Holm-Bonferroni correction
across all 53 tests. Finally, we check whether any category-level review effect is simply a
proxy for that category's `pct_late` — i.e. is this H3, or a restatement of H1/H2?""")

code(r'''items = pd.read_sql("""
    SELECT oi.order_id, dp.product_category_name_english AS category
    FROM marts.fact_order_items oi
    JOIN marts.dim_product dp ON dp.product_id = oi.product_id
    WHERE dp.product_category_name_english IS NOT NULL
""", engine)

order_cat = items.merge(
    orders[["order_id", "review_score", "delivery_delay_days", "is_late"]],
    on="order_id", how="inner")

cat_counts = order_cat["category"].value_counts()
top_categories = cat_counts[cat_counts >= 100].index.tolist()
cat_sub = order_cat[order_cat["category"].isin(top_categories)]
print(f"{len(top_categories)} of {cat_counts.shape[0]} categories have >=100 reviewed orders "
      f"({len(cat_sub):,} order-category rows, {cat_sub['order_id'].nunique():,} distinct orders)")

cat_groups = {c: g["review_score"].values for c, g in cat_sub.groupby("category")}
H3, p3 = stats.kruskal(*cat_groups.values())
eps2_cat = epsilon_sq(H3, len(cat_sub))
print(f"\nKruskal-Wallis across {len(cat_groups)} categories: H={H3:,.1f}, p={p3:.2e}, "
      f"epsilon^2={eps2_cat:.4f} ({interpret_eps2(eps2_cat)})")

grand_mean = cat_sub["review_score"].mean()
print(f"Grand mean review_score = {grand_mean:.3f}")''')

code(r"""rows = []
for c, g in cat_groups.items():
    rest = cat_sub.loc[cat_sub["category"] != c, "review_score"].values
    _, pv = stats.mannwhitneyu(g, rest, alternative="two-sided")
    rows.append({"category": c, "n": len(g), "mean_review": g.mean(),
                  "diff_vs_grand_mean": g.mean() - grand_mean, "p_raw": pv})
cat_test = pd.DataFrame(rows)
reject3, p_holm3_cat = holm(cat_test["p_raw"])
cat_test["p_holm"] = p_holm3_cat
cat_test["significant"] = reject3
cat_test = cat_test.sort_values("mean_review").reset_index(drop=True)

print(f"{cat_test['significant'].sum()} of {len(cat_test)} categories significant after Holm correction\n")
print("5 lowest-rated categories:")
print(cat_test.head(5)[["category", "n", "mean_review", "diff_vs_grand_mean", "p_holm", "significant"]])
print("\n5 highest-rated categories:")
print(cat_test.tail(5)[["category", "n", "mean_review", "diff_vs_grand_mean", "p_holm", "significant"]])""")

code(r"""sig = cat_test[cat_test["significant"]].sort_values("diff_vs_grand_mean")
colors3 = ["#c0392b" if d < 0 else "#27ae60" for d in sig["diff_vs_grand_mean"]]

fig, ax = plt.subplots(figsize=(9, 7))
ax.hlines(y=sig["category"], xmin=0, xmax=sig["diff_vs_grand_mean"], color=colors3, linewidth=2)
ax.scatter(sig["diff_vs_grand_mean"], sig["category"], color=colors3, s=40, zorder=3)
ax.axvline(0, color="black", linewidth=1)
ax.set_xlabel(f"mean_review - grand mean ({grand_mean:.2f})")
ax.set_title(f"{len(sig)} of {len(cat_test)} categories significantly differ from the\n"
             f"grand-mean review score (Holm-corrected one-vs-rest Mann-Whitney)")
for y, (d, n) in enumerate(zip(sig["diff_vs_grand_mean"], sig["n"])):
    ax.text(d + (0.005 if d > 0 else -0.005), y, f"n={n:,}",
            va="center", ha="left" if d > 0 else "right", fontsize=8, color="#555")
plt.tight_layout()
plt.show()""")

code(r"""cat_delay = cat_sub.groupby("category").agg(
    n=("review_score", "count"), mean_review=("review_score", "mean"),
    pct_late=("is_late", "mean")).loc[top_categories]
r_confound = cat_delay["mean_review"].corr(cat_delay["pct_late"])
print(f"Correlation across {len(cat_delay)} categories between mean_review and pct_late: "
      f"r={r_confound:.3f}")
print(f"Overall pct_late = {100*orders['is_late'].mean():.2f}%\n")
print("Worst- vs best-rated category, pct_late comparison:")
print((100 * cat_delay.loc[["office_furniture", "books_general_interest"], ["pct_late"]]).round(2)
      .join(cat_delay.loc[["office_furniture", "books_general_interest"], ["n", "mean_review"]]))""")

md(r"""### Finding: category matters (16 of 53 significant), but it's a *different* effect from delivery delay

The omnibus Kruskal-Wallis is significant (H=1,127.4, p≈0) but with **epsilon²=0.010
("small")** — an order of magnitude smaller than the delay-bucket effect (0.106, Section 2).
After Holm correction, **16 of 53 categories (30%)** differ significantly from the grand-mean
review score (4.156). `office_furniture` is the single worst category (mean 3.51, n=1,654,
p_holm=1.4e-72) and `books_general_interest` the best (mean 4.51, n=532, p_holm=5.7e-14) — a
full **1-star gap** between the two extremes.

Critically, **the category effect is largely independent of delivery delay**: across the 53
categories, the correlation between `mean_review` and `pct_late` is just **r=-0.11** —
`office_furniture`'s 8.8% late-rate is close to the 7.8% overall average, so its low review
score is *not* a delay story. This points at **product-specific factors** — assembly
complexity, damage-in-transit for bulky/fragile items (furniture, electronics), or
expectation mismatches for technical categories — as a *second, independent* lever for
review-score management, worth a dedicated complaint-text/return-reason analysis in a
follow-up project.""")


# ============================================================================
# Section 4: Regional effects (H4, extends NB3)
# ============================================================================
md(r"""## 4. Regional Effects on Review Score and Delivery Delay (H4, extends NB3)

NB3 mapped `pct_late` and `avg_review_score` by *state*; here we test the coarser 5-region
(`BR_REGION`) split formally for **both** outcomes, since NB3 F25/F26 suggested the
delay → review relationship might itself vary by region.

**H0 (review):** `review_score` has the same distribution across the 5 regions.
**H0 (delay):** `delivery_delay_days` has the same distribution across the 5 regions.

Both are tested with Kruskal-Wallis + epsilon²; the review-score test is followed by the same
10-pair Holm-corrected post-hoc design as Section 2, plus a chi-square test of
`region x review_cat` (Cramér's V).""")

code(r"""region_groups_rev = {r: g["review_score"].values for r, g in orders.groupby("region")}
H_rev, p_rev = stats.kruskal(*region_groups_rev.values())
eps2_rev = epsilon_sq(H_rev, len(orders))

region_groups_delay = {r: g["delivery_delay_days"].values for r, g in orders.groupby("region")}
H_delay, p_delay = stats.kruskal(*region_groups_delay.values())
eps2_delay = epsilon_sq(H_delay, len(orders))

print(f"review_score ~ region:        H={H_rev:,.1f}, p={p_rev:.2e}, eps^2={eps2_rev:.4f} ({interpret_eps2(eps2_rev)})")
print(f"delivery_delay_days ~ region:  H={H_delay:,.1f}, p={p_delay:.2e}, eps^2={eps2_delay:.4f} ({interpret_eps2(eps2_delay)})")

region_summary = orders.groupby("region").agg(
    n_orders=("order_id", "size"),
    mean_review_score=("review_score", "mean"),
    mean_delivery_delay_days=("delivery_delay_days", "mean"),
    pct_late=("is_late", "mean"),
).reindex(REGION_ORDER)
region_summary["pct_late"] = 100 * region_summary["pct_late"]
region_summary""")

code(r"""pairs4, pvals4 = [], []
for i in range(len(REGION_ORDER)):
    for j in range(i + 1, len(REGION_ORDER)):
        _, pv = stats.mannwhitneyu(region_groups_rev[REGION_ORDER[i]], region_groups_rev[REGION_ORDER[j]],
                                    alternative="two-sided")
        pairs4.append((REGION_ORDER[i], REGION_ORDER[j]))
        pvals4.append(pv)
reject4, p_holm4 = holm(pvals4)
posthoc4 = pd.DataFrame({"region_1": [a for a, b in pairs4], "region_2": [b for a, b in pairs4],
                          "p_raw": pvals4, "p_holm": p_holm4, "significant": reject4})

ct4 = pd.crosstab(orders["region"], orders["review_cat"]).reindex(REGION_ORDER)
v4, chi2_4, pchi4, dof4 = cramers_v(ct4)
print(f"Chi-square (region x review_cat): chi2={chi2_4:,.1f}, dof={dof4}, p={pchi4:.2e}")
print(f"Cramer's V = {v4:.4f} ({interpret_v(v4)})\n")
print(f"{reject4.sum()} of {len(reject4)} pairwise region comparisons (review_score) significant after Holm")
posthoc4""")

code(r"""fig, axes = plt.subplots(1, 2, figsize=(13, 5))

order_by_review = region_summary.sort_values("mean_review_score").index.tolist()
bars = axes[0].bar(order_by_review, region_summary.loc[order_by_review, "mean_review_score"],
                    color=[REGION_COLORS[r] for r in order_by_review])
axes[0].set_ylim(3.8, 4.3)
axes[0].set_title(f"mean review_score by region\n(KW ε²={eps2_rev:.4f}, {interpret_eps2(eps2_rev)})")
axes[0].set_ylabel("mean review_score")
axes[0].tick_params(axis="x", rotation=20)
for b, r in zip(bars, order_by_review):
    axes[0].text(b.get_x() + b.get_width()/2, b.get_height() + 0.005, f"{b.get_height():.3f}",
                  ha="center", fontsize=9)

mat4 = pd.DataFrame(np.nan, index=REGION_ORDER, columns=REGION_ORDER)
for (a, b), p_adj in zip(pairs4, p_holm4):
    val = -np.log10(max(p_adj, 1e-300))
    mat4.loc[a, b] = val
    mat4.loc[b, a] = val
sns.heatmap(mat4, annot=True, fmt=".1f", cmap="Reds", ax=axes[1],
            cbar_kws={"label": "-log10(p_holm)"}, linewidths=0.5, linecolor="white")
axes[1].set_title("Post-hoc pairwise significance (review_score)\n-log10(p_holm), Holm-corrected"
                   "\n(low values = not significant)")
axes[1].tick_params(axis="x", rotation=20)

plt.tight_layout()
plt.show()""")

md(r"""### Finding: regional review-score and delivery-delay differences are real but small — and don't perfectly align

Both omnibus tests reject H0 (review: H=244.4, p=1.0e-51; delay: H=929.3, p≈0), but **both
effect sizes are "negligible-to-small"** (eps²=0.0026 and 0.0097 respectively) — an order of
magnitude below the delay-bucket effect (Section 2, eps²=0.106). Regions matter, but they
explain a small fraction of the variance compared to an order's own delay outcome.

The post-hoc table reveals a counter-intuitive pairing: **North vs. Northeast is NOT
significant for review_score** (p_holm=0.338) **despite North having the BEST average
delivery_delay_days (-15.0 days, i.e. earliest)** and Northeast having the WORST avg review
score (3.97) of the 5 regions. Conversely, **South and Southeast are statistically
indistinguishable on review score** (p_holm=0.818) despite a ~1.5-day difference in average
delay. The chi-square test on `region x review_cat` is significant (Cramér's V=0.032,
"negligible") — region alone is a weak categorical predictor of "positive vs.
negative/neutral" review once the much stronger delay-bucket and `is_late` signals (Sections
1-2) are accounted for. **Practical read:** region-level KPIs (like NB3's state choropleths)
remain valuable for *operational* targeting (where to add fulfillment capacity), but region
should not be expected to carry much *predictive* weight in NB6's review/delay models —
order-level delay features will dominate.""")


# ============================================================================
# Section 5: Payment behavior (H5)
# ============================================================================
md(r"""## 5. Payment Behavior: Type, Installments, Order Value & Review (H5)

`primary_payment_type` (the payment method contributing the largest share of
`payment_value` to an order — credit_card / boleto / voucher / debit_card) and
`max_installments` are checkout-stage signals. We test three sub-hypotheses:

- **H5a:** `order_total_value` differs by `primary_payment_type` (Kruskal-Wallis + eps²).
- **H5b:** `primary_payment_type` is associated with `review_cat` (chi-square + Cramér's V) —
  i.e. does *how* a customer pays predict satisfaction?
- **H5c:** `max_installments` is correlated with `order_total_value` (Spearman + bootstrap
  95% CI) — larger purchases financed over more installments, as expected economically.""")

code(r"""print(orders["primary_payment_type"].value_counts())
pay_types = orders["primary_payment_type"].value_counts()[lambda s: s >= 100].index
pay_sub = orders[orders["primary_payment_type"].isin(pay_types)]

# H5a
pay_groups = {pt: g["order_total_value"].values for pt, g in pay_sub.groupby("primary_payment_type")}
H5a, p5a = stats.kruskal(*pay_groups.values())
eps2_5a = epsilon_sq(H5a, len(pay_sub))
print(f"\nH5a  order_total_value ~ payment_type: H={H5a:,.1f}, p={p5a:.2e}, "
      f"eps^2={eps2_5a:.4f} ({interpret_eps2(eps2_5a)})")
print(pay_sub.groupby("primary_payment_type")["order_total_value"].median()
      .sort_values().rename("median_order_total_value"))

# H5b
ct5 = pd.crosstab(pay_sub["primary_payment_type"], pay_sub["review_cat"])
v5, chi2_5, p5b, dof5 = cramers_v(ct5)
print(f"\nH5b  payment_type x review_cat: chi2={chi2_5:,.2f}, dof={dof5}, p={p5b:.2e}")
print(f"Cramer's V = {v5:.4f} ({interpret_v(v5)})")

# H5c
inst_sub = pay_sub.dropna(subset=["max_installments"])
rho5c, p5c = stats.spearmanr(inst_sub["max_installments"], inst_sub["order_total_value"])
ci5c = bootstrap_ci_spearman(inst_sub["max_installments"].values, inst_sub["order_total_value"].values)
print(f"\nH5c  installments vs order_total_value: Spearman rho={rho5c:.4f}, p={p5c:.2e}, "
      f"95% CI=[{ci5c[0]:.4f}, {ci5c[1]:.4f}]")""")

code(r"""fig, axes = plt.subplots(1, 2, figsize=(13, 5))

order_pay = pay_sub.groupby("primary_payment_type")["order_total_value"].median().sort_values().index
sns.boxplot(data=pay_sub, x="primary_payment_type", y="order_total_value", order=order_pay,
            ax=axes[0], hue="primary_payment_type", palette="deep", legend=False, fliersize=1)
axes[0].set_yscale("log")
axes[0].set_title(f"order_total_value by payment type (log scale)\nKW eps²={eps2_5a:.4f} ({interpret_eps2(eps2_5a)})")
axes[0].set_xlabel("")

inst_med = inst_sub.groupby("max_installments")["order_total_value"].median()
axes[1].scatter(inst_sub["max_installments"], inst_sub["order_total_value"], alpha=0.03, s=8, color="#3498db")
axes[1].plot(inst_med.index, inst_med.values, color="#e74c3c", marker="o", linewidth=2, label="median")
axes[1].set_yscale("log")
axes[1].set_xlabel("max_installments")
axes[1].set_ylabel("order_total_value")
axes[1].set_title(f"installments vs order value\nSpearman rho={rho5c:.3f}, 95% CI [{ci5c[0]:.3f}, {ci5c[1]:.3f}]")
axes[1].legend()

plt.tight_layout()
plt.show()""")

md(r"""### Finding: payment type predicts order *value* but not review score — a textbook "statistically significant, practically irrelevant" result

**H5a is confirmed** with a small-but-real effect (eps²=0.0092): median order value rises
from **R$81.12 (voucher) → R$89.63 (debit) → R$93.65 (boleto) → R$109.31 (credit card)** —
consistent with credit cards being the default for larger, installment-financed purchases.

**H5b, by contrast, is the most important *negative* finding in this notebook.** The
chi-square test is technically significant (p=0.013) — but **Cramér's V = 0.009**, an order
of magnitude below even the "negligible" threshold. At n=95,823, a p-value below 0.05 says
almost nothing about practical importance; **how a customer pays carries essentially zero
information about whether they'll leave a good or bad review**, in sharp contrast to
`is_late` (Cramér's V=0.372, Section 1). This is included deliberately as a **methodological
demonstration**: a less careful analysis reporting "p=0.013, payment type significantly
affects reviews!" without an effect size would be actively misleading.

**H5c is confirmed** and matches economic intuition: `max_installments` and
`order_total_value` are positively correlated (Spearman rho=0.381, 95% CI [0.376, 0.387],
entirely above zero) — bigger purchases get split into more installments, a normal
Brazilian e-commerce financing pattern with no satisfaction implications (per H5b).""")


# ============================================================================
# Section 6: Distance vs delivery outcomes (H6, extends NB3 F27)
# ============================================================================
md(r"""## 6. Distance vs. Delivery Outcomes — Formal Tests (H6, extends NB3 F27)

NB3 F27 showed `actual_delivery_days`, `pct_late`, freight share, and review score all move
with binned haversine distance. Here we test the underlying continuous relationships
formally at the order level (n≈94,726 single-seller delivered orders, 98.2% of all
delivered orders — identical sample to NB3 Section 4), with Spearman correlations +
bootstrap 95% CIs, plus a direct test of whether `distance_km` itself differs between late
and on-time orders.

- **H6a:** `distance_km` vs `actual_delivery_days` — expect strong positive correlation.
- **H6b:** `distance_km` vs `delivery_delay_days` — expect weak correlation (NB3: estimates
  already scale with distance).
- **H6c:** `distance_km` vs `freight_value_total` — expect strong positive correlation.
- **H6d:** `distance_km` differs between late and on-time orders (Mann-Whitney + Cliff's
  delta).""")

code(r'''order_geo = pd.read_sql("""
    SELECT
        fo.order_id, fo.actual_delivery_days, fo.delivery_delay_days,
        fo.freight_value_total, fo.is_late,
        dc.customer_latitude, dc.customer_longitude,
        ds.seller_latitude, ds.seller_longitude
    FROM marts.fact_orders fo
    JOIN marts.dim_customer dc ON dc.customer_unique_id = fo.customer_unique_id
    JOIN marts.fact_order_items foi ON foi.order_id = fo.order_id AND foi.order_item_id = 1
    JOIN marts.dim_seller ds ON ds.seller_id = foi.seller_id
    WHERE fo.is_delivered AND fo.n_distinct_sellers = 1
      AND fo.delivery_delay_days IS NOT NULL AND fo.is_late IS NOT NULL
      AND dc.customer_latitude IS NOT NULL AND ds.seller_latitude IS NOT NULL
""", engine)

def haversine_km(lat1, lon1, lat2, lon2):
    R = 6371.0
    lat1, lon1, lat2, lon2 = map(np.radians, [lat1, lon1, lat2, lon2])
    dlat, dlon = lat2 - lat1, lon2 - lon1
    a = np.sin(dlat/2)**2 + np.cos(lat1)*np.cos(lat2)*np.sin(dlon/2)**2
    return 2 * R * np.arcsin(np.sqrt(a))

order_geo["distance_km"] = haversine_km(order_geo["customer_latitude"], order_geo["customer_longitude"],
                                          order_geo["seller_latitude"], order_geo["seller_longitude"])
print(f"order_geo: {len(order_geo):,} single-seller delivered orders")

results = []
for label, col in [("actual_delivery_days (H6a)", "actual_delivery_days"),
                    ("delivery_delay_days (H6b)", "delivery_delay_days"),
                    ("freight_value_total (H6c)", "freight_value_total")]:
    rho, p = stats.spearmanr(order_geo["distance_km"], order_geo[col])
    ci = bootstrap_ci_spearman(order_geo["distance_km"].values, order_geo[col].values)
    results.append({"relationship": f"distance_km vs {label}", "spearman_rho": rho, "p_value": p,
                     "ci_lo": ci[0], "ci_hi": ci[1]})
h6_table = pd.DataFrame(results)
print(h6_table.to_string(index=False))

late_d = order_geo.loc[order_geo["is_late"], "distance_km"]
ontime_d = order_geo.loc[~order_geo["is_late"], "distance_km"]
U_h6d, p_h6d = stats.mannwhitneyu(late_d, ontime_d, alternative="two-sided")
delta_h6d = cliffs_delta(late_d, ontime_d)
print(f"\nH6d  distance_km: late (mean={late_d.mean():.1f} km) vs on-time (mean={ontime_d.mean():.1f} km)")
print(f"     Mann-Whitney p={p_h6d:.2e}, Cliff's delta={delta_h6d:.3f} ({interpret_cliffs_delta(delta_h6d)})")''')

code(r"""fig, axes = plt.subplots(1, 2, figsize=(13, 5))

hb = axes[0].hexbin(order_geo["distance_km"], order_geo["actual_delivery_days"],
                     gridsize=50, cmap="viridis", mincnt=1, bins="log")
axes[0].set_xlabel("distance_km (haversine, seller -> customer)")
axes[0].set_ylabel("actual_delivery_days")
axes[0].set_title(f"distance vs actual delivery time\nSpearman rho={h6_table.iloc[0]['spearman_rho']:.3f}")
fig.colorbar(hb, ax=axes[0], label="log10(count)")

y6 = np.arange(len(h6_table))
colors6 = ["#3498db" if r > 0 else "#e74c3c" for r in h6_table["spearman_rho"]]
axes[1].barh(y6, h6_table["spearman_rho"], color=colors6,
              xerr=[h6_table["spearman_rho"] - h6_table["ci_lo"], h6_table["ci_hi"] - h6_table["spearman_rho"]],
              capsize=4)
axes[1].set_yticks(y6)
axes[1].set_yticklabels(["vs actual_delivery_days\n(H6a)", "vs delivery_delay_days\n(H6b)", "vs freight_value_total\n(H6c)"])
axes[1].axvline(0, color="black", linewidth=1)
axes[1].set_xlabel("Spearman rho (with 95% bootstrap CI)")
axes[1].set_title("distance_km correlations")

plt.tight_layout()
plt.show()""")

md(r"""### Finding: distance drives delivery time and freight cost, but not delivery delay — confirming NB3's "estimate already accounts for distance"

**H6a confirmed** — distance_km vs actual_delivery_days: Spearman rho=0.543 (95% CI [0.538,
0.548]), a genuine moderate-to-strong relationship: farther orders simply take longer in
absolute terms.

**H6c confirmed** — distance_km vs freight_value_total: rho=0.593 (95% CI [0.588, 0.598]),
the strongest of the three — freight pricing is heavily distance-based, as expected.

**H6b is the key result**: distance_km vs delivery_delay_days is **weak and negative**
(rho=-0.179, 95% CI [-0.185, -0.172]) — the *opposite sign* from H6a/H6c. Combined with NB3's
finding that `estimated_delivery_days` itself scales with distance, this confirms Olist's
SLA estimation already "prices in" distance: farther orders take longer *in absolute terms*
but are not more likely to arrive *later than promised* — if anything, slightly less so.

**H6d confirmed but small**: late orders average 739.8 km vs. 589.1 km for on-time orders
(Mann-Whitney p=5.9e-76, Cliff's delta=0.126, "negligible-to-small"). Distance is a real but
*minor* contributor to lateness — an order of magnitude smaller than the buffer-thinness
effect from NB3 F25 (r=0.72). **Taken together, H6a-d say: distance is a strong predictor of
how long delivery takes, and a weak predictor of whether delivery is late** — two genuinely
different operational questions that are easy to conflate.""")


# ============================================================================
# Section 7: Effect-size leaderboard + Key Findings Summary
# ============================================================================
md(r"""## 7. Effect-Size Leaderboard & Key Findings Summary

Sections 1-4 all tested factors against the *same* outcome (`review_score`) using the *same*
effect size (epsilon-squared from Kruskal-Wallis), which makes them directly comparable. The
chart below ranks H1-H4 by epsilon² — the single clearest answer this notebook can give to
"what actually drives review score?".""")

code(r"""leaderboard = pd.DataFrame([
    {"factor": "delivery_delay_days bucket (5 levels) — H2", "eps2": eps2,         "section": "Section 2"},
    {"factor": "is_late (binary) — H1",                       "eps2": eps2_islate,  "section": "Section 1"},
    {"factor": "product_category (53 levels) — H3",           "eps2": eps2_cat,     "section": "Section 3"},
    {"factor": "region (5 levels) — H4",                       "eps2": eps2_rev,     "section": "Section 4"},
]).sort_values("eps2", ascending=True)

fig, ax = plt.subplots(figsize=(9, 4.5))
colors_lb = ["#8e44ad", "#e67e22", "#27ae60", "#2980b9"]
bars = ax.barh(leaderboard["factor"], leaderboard["eps2"], color=colors_lb)
for b, v in zip(bars, leaderboard["eps2"]):
    ax.text(v + 0.0015, b.get_y() + b.get_height()/2, f"{v:.4f} ({interpret_eps2(v)})",
            va="center", fontsize=9)
ax.set_xlabel("epsilon-squared (Kruskal-Wallis effect size on review_score)")
ax.set_title("What actually drives review_score? Effect-size comparison, H1-H4")
ax.set_xlim(0, leaderboard["eps2"].max() * 1.4)
plt.tight_layout()
plt.show()""")

md(r"""Continuing the numbering from Notebooks 1-3 (findings 1-30):

| # | Finding | Evidence | Cross-reference |
|---|---|---|---|
| 31 | **`is_late` is confirmed as one of the two strongest review-score predictors tested**: Mann-Whitney p≈0, Cliff's delta=-0.554 ("large"), eps²=0.086 ("medium"); mean review falls 4.29 → 2.57. Chi-square on `review_cat`: Cramér's V=0.372 ("medium-large") — 82.8% of on-time orders are 4-5 stars vs only 34.6% of late orders. | Section 1 | Confirms NB1 F14 formally |
| 32 | **All 10 pairwise delay-bucket comparisons remain significant after Holm correction**, including Early vs On-time (p_holm=5.0e-17, only a 0.16-star gap on n=85,173 vs 2,990). Delay-bucket eps²=0.106 ("medium", just short of "large") is the **largest effect size in this notebook**. | Section 2 | Refines NB1 F14 / Section 7 |
| 33 | **16 of 53 product categories significantly differ from the grand-mean review score** (Holm-corrected), eps²=0.010 ("small"). `office_furniture` (3.51) vs `books_general_interest` (4.51) — a 1-star gap. The category effect is independent of delay (r=-0.11 between category mean_review and pct_late). | Section 3 | New analysis |
| 34 | **Region matters for review_score (eps²=0.0026) and delay (eps²=0.0097), but both are "negligible-to-small."** North and Northeast are NOT significantly different on review_score (p_holm=0.338) despite North having the best avg delay; South and Southeast are also indistinguishable (p_holm=0.818). | Section 4 | Extends NB3 F24-26 |
| 35 | **Payment type predicts order value (eps²=0.0092: credit card median R$109.31 vs voucher R$81.12) but NOT review score** (Cramér's V=0.009 despite p=0.013) — a deliberate demonstration that statistical significance ≠ practical significance at n~96K. Installments correlate with order value (rho=0.381, 95% CI [0.376, 0.387]) as expected. | Section 5 | New analysis |
| 36 | **Distance predicts delivery time (rho=0.543) and freight (rho=0.593) strongly, but delivery *delay* only weakly and negatively (rho=-0.179)** — confirms NB3's "estimate already scales with distance." Late orders average ~150 km farther than on-time orders (Cliff's delta=0.126, "negligible-to-small"). | Section 6 | Formalizes NB3 F27 |

**Overall takeaway:** the effect-size leaderboard above gives a clear, defensible ranking of
what actually moves `review_score`: **the order's own delivery-delay outcome (F31-F32,
eps²=0.086-0.106) dwarfs every other factor tested** — product category (F33, eps²=0.010),
region (F34, eps²=0.003), and payment behavior (F35, Cramér's V=0.009, statistically
significant but practically zero). This has a direct, falsifiable implication for **Notebook
6's predictive model**: a classifier for "will this order get a bad review" should be built
*primarily* on delivery-timing features (and the upstream signals that predict delivery
timing, like `estimated_delivery_days` and `distance_km` from H6), with category and region
as secondary refinements — not the reverse. It also gives Operations a clean prioritization:
**fixing late deliveries (F31-32) would move review scores roughly 10x more than any
category-specific or regional intervention (F33-34)**, even before accounting for the
revenue-concentration arguments from NB3.""")


nb["cells"] = cells
nb["metadata"] = {
    "kernelspec": {"display_name": "Python 3 (.venv)", "language": "python", "name": "python3"},
    "language_info": {"name": "python", "pygments_lexer": "ipython3",
                       "codemirror_mode": {"name": "ipython", "version": 3},
                       "file_extension": ".py", "mimetype": "text/x-python",
                       "nbconvert_exporter": "python"},
}

with open("notebooks/04_hypothesis_testing.ipynb", "w") as f:
    nbf.write(nb, f)

print(f"Wrote {len(cells)} cells to notebooks/04_hypothesis_testing.ipynb")
