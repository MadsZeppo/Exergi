"""Download and convert the verified CC0 CRAN completejourney 1.1.0 universe."""

from __future__ import annotations

import argparse
import hashlib
import json
import tarfile
import urllib.request
from datetime import UTC, datetime
from pathlib import Path

import pandas as pd
import pyreadr

VERSION = "1.1.0"
PACKAGE_URL = (
    "https://cran.r-project.org/src/contrib/Archive/completejourney/completejourney_1.1.0.tar.gz"
)
TRANSACTIONS_URL = (
    "https://github.com/bradleyboehmke/completejourney/raw/master/data/transactions.rds"
)


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _download(url: str, target: Path) -> None:
    if not target.exists():
        urllib.request.urlretrieve(url, target)


def _read_single(path: Path) -> pd.DataFrame:
    result = pyreadr.read_r(path)
    if len(result) != 1:
        raise ValueError(f"expected one R object in {path}, found {list(result)}")
    return next(iter(result.values()))


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, default=Path("data/raw/dunnhumby/complete-journey"))
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=True)
    package = args.output / f"completejourney_{VERSION}.tar.gz"
    transactions_rds = args.output / "transactions.rds"
    _download(PACKAGE_URL, package)
    _download(TRANSACTIONS_URL, transactions_rds)
    extract_root = args.output / "cran-package"
    if not extract_root.exists():
        with tarfile.open(package, "r:gz") as archive:
            archive.extractall(extract_root, filter="data")
    package_root = extract_root / "completejourney"
    description = (package_root / "DESCRIPTION").read_text(encoding="utf-8")
    if "License: CC0" not in description or f"Version: {VERSION}" not in description:
        raise ValueError("CRAN package version/license verification failed")

    transactions = _read_single(transactions_rds)
    campaigns = _read_single(package_root / "data/campaigns.rda")
    campaign_desc = _read_single(package_root / "data/campaign_descriptions.rda")
    products = _read_single(package_root / "data/products.rda")
    coupons = _read_single(package_root / "data/coupons.rda")
    redemptions = _read_single(package_root / "data/coupon_redemptions.rda")
    origin = pd.Timestamp(transactions["transaction_timestamp"].min()).normalize()

    transaction_data = transactions.rename(
        columns={
            "household_id": "HOUSEHOLD_KEY",
            "basket_id": "BASKET_ID",
            "product_id": "PRODUCT_ID",
            "quantity": "QUANTITY",
            "sales_value": "SALES_VALUE",
            "retail_disc": "RETAIL_DISC",
            "coupon_disc": "COUPON_DISC",
            "coupon_match_disc": "COUPON_MATCH_DISC",
            "store_id": "STORE_ID",
            "week": "WEEK_NO",
            "transaction_timestamp": "TRANSACTION_TIMESTAMP",
        }
    )
    transaction_data["DAY"] = (
        pd.to_datetime(transaction_data["TRANSACTION_TIMESTAMP"]).dt.normalize() - origin
    ).dt.days + 1
    transaction_data.to_csv(
        args.output / "transaction_data.csv.gz", index=False, compression="gzip"
    )

    products.rename(
        columns={
            "product_id": "PRODUCT_ID",
            "manufacturer_id": "MANUFACTURER",
            "department": "DEPARTMENT",
            "brand": "BRAND",
            "product_category": "COMMODITY_DESC",
            "product_type": "SUB_COMMODITY_DESC",
            "package_size": "CURR_SIZE_OF_PRODUCT",
        }
    ).to_csv(args.output / "product.csv.gz", index=False, compression="gzip")
    campaigns.rename(columns={"campaign_id": "CAMPAIGN", "household_id": "HOUSEHOLD_KEY"}).to_csv(
        args.output / "campaign_table.csv.gz", index=False, compression="gzip"
    )

    campaign_output = campaign_desc.rename(
        columns={
            "campaign_id": "CAMPAIGN",
            "campaign_type": "DESCRIPTION",
            "start_date": "START_DATE",
            "end_date": "END_DATE",
        }
    )
    campaign_output["START_DAY"] = (
        pd.to_datetime(campaign_output["START_DATE"]) - origin
    ).dt.days + 1
    campaign_output["END_DAY"] = (pd.to_datetime(campaign_output["END_DATE"]) - origin).dt.days + 1
    campaign_output.to_csv(args.output / "campaign_desc.csv.gz", index=False, compression="gzip")

    coupons.rename(
        columns={"coupon_upc": "COUPON_UPC", "product_id": "PRODUCT_ID", "campaign_id": "CAMPAIGN"}
    ).to_csv(args.output / "coupon.csv.gz", index=False, compression="gzip")
    redemption_output = redemptions.rename(
        columns={
            "household_id": "HOUSEHOLD_KEY",
            "coupon_upc": "COUPON_UPC",
            "campaign_id": "CAMPAIGN",
            "redemption_date": "REDEMPTION_TIMESTAMP",
        }
    )
    redemption_output["REDEMPTION_DATE"] = (
        pd.to_datetime(redemption_output["REDEMPTION_TIMESTAMP"]) - origin
    ).dt.days + 1
    redemption_output.to_csv(args.output / "coupon_redempt.csv.gz", index=False, compression="gzip")

    campaign_households = set(campaigns["household_id"].astype(str))
    transaction_households = set(transactions["household_id"].astype(str))
    metadata = {
        "source": "CRAN completejourney 1.1.0 and its documented source GitHub repository",
        "package_url": PACKAGE_URL,
        "transactions_url": TRANSACTIONS_URL,
        "package_version": VERSION,
        "license": "CC0",
        "downloaded_at": datetime.now(UTC).isoformat(),
        "package_sha256": _sha256(package),
        "transactions_rds_sha256": _sha256(transactions_rds),
        "transactions": len(transactions),
        "transaction_households": len(transaction_households),
        "campaign_rows": len(campaigns),
        "campaign_households": len(campaign_households),
        "campaigns": int(campaigns["campaign_id"].nunique()),
        "coupons": len(coupons),
        "coupon_redemptions": len(redemptions),
        "campaign_households_missing_transactions": len(
            campaign_households - transaction_households
        ),
        "scope_warning": (
            "CC0 CRAN 1.1.0 universe: 2,469 households over one year; not the original "
            "two-year 2,500-household Source Files release."
        ),
        "derived_calendar": "DAY fields are derived from CRAN timestamps with DAY 1 at 2017-01-01",
    }
    (args.output / "cran_source_metadata.json").write_text(
        json.dumps(metadata, indent=2), encoding="utf-8"
    )
    print(json.dumps(metadata, indent=2))


if __name__ == "__main__":
    main()
