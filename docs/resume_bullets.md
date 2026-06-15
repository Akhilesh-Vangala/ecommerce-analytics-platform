# Resume Bullets & Positioning

This project — **End-to-End E-Commerce Retail & Fulfillment Analytics (Olist Brazil, modeled as an Amazon Retail/Marketplace/Ops analog)** — is the flagship portfolio piece for Data Analyst / Business Analyst applications. This doc translates the finished work (see `docs/CASE_STUDY.md` for the full narrative) into resume-ready bullets, a one-line project header, and tailoring guidance.

## Why this project fits the Amazon Data Analyst role

Amazon DA/BA postings consistently ask for: advanced SQL (window functions, CTEs), Python for statistical analysis, dashboarding (their internal tools play the role Tableau plays here), and — most importantly — the ability to go from ambiguous data to a quantified business recommendation ("Dive Deep," "Customer Obsession," "Ownership" in LP terms). This project deliberately maps onto Amazon's actual business shape:

- **3rd-party marketplace** (Olist sellers = Amazon Marketplace sellers) → Domain 4 (seller concentration, HHI, Pareto).
- **Fulfillment network with delivery promises** (estimated vs. actual delivery date) → Domain 3 (OTD, cycle-time stages, promise-date calibration).
- **Customer Obsession thread**: delivery delay → review score → repeat-purchase behavior, tying Ops back to Retail (Q3.5, Domain 2).
- **Growth/retention**: GMV trend, category mix, RFM/cohort retention — the core "is the business healthy" questions any Retail BA owns.

The project is **not** a toy notebook — it has a real layered warehouse, a documented data-quality framework, 27 cataloged SQL queries with business questions and findings, 6 statistics/ML notebooks, a 7-page Tableau dashboard, and a full data dictionary. That breadth is what should differentiate it from the typical "Kaggle EDA notebook" portfolio project.

---

## Resume header (Projects section)

> **End-to-End E-Commerce Analytics — Revenue, Retention & Fulfillment Ops** (PostgreSQL, SQL, Python, scikit-learn, Tableau)
> Built a production-style analytics warehouse and 27-query SQL/Python/ML analysis of a 99K-order marketplace; identified a 96.9% one-time-buyer problem, root-caused a fulfillment crisis, and shipped a 7-page executive dashboard.

---

## Tight bullets (pick 3-5 depending on space and the JD's emphasis)

1. **Data architecture & quality** — Architected a layered PostgreSQL warehouse (raw → staging → star-schema marts, with Redshift-ready DISTKEY/SORTKEY DDL) for 99K orders, 96K customers, and 3,095 sellers, backed by an automated data-quality suite that flagged and quantified 3 distinct timestamp-integrity issues.

2. **Advanced SQL** — Authored 27 production-grade SQL queries (window functions — `NTILE`, `RANK`, `LAG`, `PERCENTILE_CONT`, `ROWS BETWEEN` frames; CTEs) across revenue/growth, customer RFM/cohort retention, fulfillment operations, and seller-marketplace domains, each tied to a documented business question and finding.

3. **Customer retention analysis** — Used cohort analysis and K-Means segmentation to uncover a 96.9% one-time-buyer rate and 0.48% month-1 retention (vs. a 20-40% industry benchmark), and sized a ~R$4.6M (29% of GMV) win-back opportunity among high-value lapsed customers.

4. **Root-cause / anomaly investigation** — Drilled a monthly fulfillment KPI down to weekly and state-level grain to root-cause a late-delivery spike (from a ~8% baseline to a 29% weekly peak across 10+ states), tracing it to a national-holiday carrier backlog and quantifying its cost: 1-star review rate rose from 6.6% to 68.8% once deliveries exceeded 4 days late.

5. **Predictive modeling & methodology rigor** — Built Random Forest classifiers for late-delivery risk (AUC=0.742) and negative-review risk (AUC≈0.745) using a time-based train/test split, after first demonstrating that a naive random split overstates performance (AUC=0.481, worse than chance) due to temporal leakage — then used feature importance to surface actionable, order-time risk signals.

6. **Marketplace & logistics strategy** — Quantified marketplace concentration risk (top 10% of 3,095 sellers generate 67.6% of revenue; one state holds 64.4% of seller-side revenue vs. 62.5% of customer demand) and cross-state logistics penalties (+76% freight cost, 2.5x transit time), recommending regional fulfillment hubs and targeted seller recruitment in underserved high-AOV states.

7. **Dashboarding & storytelling** — Designed a 7-page interactive Tableau dashboard from 24 curated SQL/Python extracts, translating 27 SQL queries and 6 Jupyter notebooks of statistical/ML analysis into an executive-ready narrative covering revenue trends, customer segments, fulfillment SLAs, and seller scorecards.

---

## Extended version (LinkedIn "Featured" project / portfolio README intro)

> Built an end-to-end, production-style analytics project on a 99,441-order Brazilian e-commerce marketplace (Olist), deliberately framed as an Amazon Retail + Marketplace + Fulfillment analog. Designed a layered PostgreSQL warehouse (raw → staging → star-schema marts) with Redshift-compatible DDL and an automated data-quality framework. Wrote 27 advanced SQL queries across four domains — revenue & growth, customer RFM/cohort retention, fulfillment operations, and seller/marketplace performance — and backed them with six Jupyter notebooks covering EDA, time-series decomposition, geospatial analysis, hypothesis testing, K-Means segmentation, and predictive modeling (Random Forest, AUC 0.74). Headline findings: a 96.9% one-time-buyer rate against a 0.48% month-1 retention benchmark, a ~R$4.6M win-back opportunity in lapsed high-value customers, and a root-caused 2018 fulfillment crisis linking a holiday carrier backlog to a measurable collapse in review scores. Delivered as a 7-page Tableau dashboard, a full data dictionary, and a documented SQL query catalog.

---

## Tailoring guidance by JD emphasis

| If the JD emphasizes... | Lead with bullets |
|---|---|
| "Advanced SQL", "complex queries", "data warehousing" | 1, 2 |
| "Customer analytics", "segmentation", "retention/lifecycle" | 3 |
| "Root cause analysis", "operational metrics", "anomaly detection" | 4 |
| "Statistical modeling", "machine learning", "experimentation rigor" | 5 |
| "Marketplace", "seller/vendor analytics", "supply chain/logistics" | 6 |
| "Dashboards", "data visualization", "stakeholder communication" | 7 |

For most entry-level Amazon DA/BA postings, **1, 2, 3 (or 4), and 7** is a strong default set of 4 — it covers data engineering fundamentals, advanced SQL, a headline business insight, and communication/dashboarding.
