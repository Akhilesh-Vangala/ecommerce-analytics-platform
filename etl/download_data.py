"""Download the Olist Brazilian E-Commerce Public Dataset from Kaggle into data/raw/.

One-time setup (Kaggle API credentials):
    1. Create a Kaggle account, then go to https://www.kaggle.com/settings/account
       -> "Create New Token". This downloads kaggle.json.
    2. Place it at ~/.kaggle/kaggle.json (chmod 600), or set the KAGGLE_USERNAME
       and KAGGLE_KEY environment variables.

Usage:
    .venv/bin/python etl/download_data.py
"""
from __future__ import annotations

import logging
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
RAW_DATA_DIR = PROJECT_ROOT / "data" / "raw"
KAGGLE_DATASET = "olistbr/brazilian-ecommerce"

# Files expected after download - mirrors CSV_TABLE_MAP in load_raw_data.py
EXPECTED_FILES = [
    "olist_orders_dataset.csv",
    "olist_order_items_dataset.csv",
    "olist_order_payments_dataset.csv",
    "olist_order_reviews_dataset.csv",
    "olist_customers_dataset.csv",
    "olist_products_dataset.csv",
    "olist_sellers_dataset.csv",
    "olist_geolocation_dataset.csv",
    "product_category_name_translation.csv",
]

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger("download_data")


def main() -> int:
    RAW_DATA_DIR.mkdir(parents=True, exist_ok=True)

    missing = [f for f in EXPECTED_FILES if not (RAW_DATA_DIR / f).exists()]
    if not missing:
        log.info("All %d raw files already present in %s - nothing to do.", len(EXPECTED_FILES), RAW_DATA_DIR)
        return 0

    try:
        from kaggle.api.kaggle_api_extended import KaggleApi
    except OSError as e:
        log.error(
            "Kaggle API credentials not found (%s). Create an API token at "
            "https://www.kaggle.com/settings/account and save it to "
            "~/.kaggle/kaggle.json (chmod 600), or set KAGGLE_USERNAME / KAGGLE_KEY "
            "env vars. See the module docstring for details.",
            e,
        )
        return 1
    except ImportError:
        log.error(
            "The 'kaggle' package is not installed. Run: pip install kaggle "
            "(it's listed in requirements.txt)."
        )
        return 1

    api = KaggleApi()
    api.authenticate()

    log.info("Downloading dataset '%s' to %s ...", KAGGLE_DATASET, RAW_DATA_DIR)
    api.dataset_download_files(KAGGLE_DATASET, path=str(RAW_DATA_DIR), unzip=True)

    still_missing = [f for f in EXPECTED_FILES if not (RAW_DATA_DIR / f).exists()]
    if still_missing:
        log.error("Download completed but expected files are still missing: %s", still_missing)
        return 1

    log.info("Download complete - all %d raw files present in %s.", len(EXPECTED_FILES), RAW_DATA_DIR)
    log.info("Next step: .venv/bin/python etl/load_raw_data.py")
    return 0


if __name__ == "__main__":
    sys.exit(main())
