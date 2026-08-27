"""Authorized-local-file ingestion for Dunnhumby Complete Journey."""

from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import polars as pl


class DunnhumbyDataset:
    STRING_COLUMNS = frozenset(
        {
            "HOUSEHOLD_KEY",
            "BASKET_ID",
            "PRODUCT_ID",
            "STORE_ID",
            "CAMPAIGN",
            "COUPON_UPC",
        }
    )
    FILES: dict[str, tuple[str, ...]] = {
        "transaction_data": ("transaction_data.csv", "transaction_data.csv.gz"),
        "product": ("product.csv", "product.csv.gz"),
        "campaign_table": ("campaign_table.csv", "campaign_table.csv.gz"),
        "campaign_desc": ("campaign_desc.csv", "campaign_desc.csv.gz"),
        "coupon": ("coupon.csv", "coupon.csv.gz"),
        "coupon_redempt": ("coupon_redempt.csv", "coupon_redempt.csv.gz"),
    }
    REQUIRED_COLUMNS: dict[str, frozenset[str]] = {
        "transaction_data": frozenset(
            {
                "HOUSEHOLD_KEY",
                "BASKET_ID",
                "DAY",
                "PRODUCT_ID",
                "QUANTITY",
                "SALES_VALUE",
                "RETAIL_DISC",
                "COUPON_DISC",
            }
        ),
        "product": frozenset({"PRODUCT_ID"}),
        "campaign_table": frozenset({"HOUSEHOLD_KEY", "CAMPAIGN"}),
        "campaign_desc": frozenset({"CAMPAIGN", "START_DAY", "END_DAY"}),
        "coupon": frozenset({"COUPON_UPC", "PRODUCT_ID", "CAMPAIGN"}),
        "coupon_redempt": frozenset({"HOUSEHOLD_KEY", "COUPON_UPC", "CAMPAIGN", "REDEMPTION_DATE"}),
    }

    def __init__(self, raw_dir: str | Path) -> None:
        self.raw_dir = Path(raw_dir)

    def available_files(self) -> list[Path]:
        return sorted(path for path in self.raw_dir.rglob("*") if path.is_file())

    def resolve_files(self) -> dict[str, Path]:
        resolved: dict[str, Path] = {}
        missing: list[str] = []
        by_name = {path.name.lower(): path for path in self.available_files()}
        for concept, candidates in self.FILES.items():
            match = next(
                (by_name[name.lower()] for name in candidates if name.lower() in by_name), None
            )
            if match is None:
                missing.append(f"{concept} ({' or '.join(candidates)})")
            else:
                resolved[concept] = match
        if missing:
            raise FileNotFoundError(
                "Dunnhumby Complete Journey is not installed or incomplete. Place authorized "
                f"files beneath {self.raw_dir}. Missing: {', '.join(missing)}. Obtain files only "
                "through an authorized source and record the applicable license/terms."
            )
        return resolved

    @staticmethod
    def sha256(path: Path) -> str:
        digest = hashlib.sha256()
        with path.open("rb") as handle:
            for chunk in iter(lambda: handle.read(1024 * 1024), b""):
                digest.update(chunk)
        return digest.hexdigest()

    def prepare(
        self,
        output_dir: str | Path,
        *,
        source: str,
        license_terms: str,
    ) -> dict[str, Any]:
        if not source.strip() or not license_terms.strip():
            raise ValueError("source and license_terms must be explicitly supplied")
        files = self.resolve_files()
        output = Path(output_dir)
        output.mkdir(parents=True, exist_ok=True)
        provenance_files: dict[str, Any] = {}
        for concept, path in files.items():
            scan = pl.scan_csv(
                path,
                infer_schema_length=10_000,
                try_parse_dates=False,
                schema_overrides={column: pl.String for column in self.STRING_COLUMNS},
            )
            columns = scan.collect_schema().names()
            missing = self.REQUIRED_COLUMNS[concept] - set(columns)
            if missing:
                raise ValueError(f"{path} missing required columns: {sorted(missing)}")
            target = output / f"{concept}.parquet"
            scan.sink_parquet(target, compression="zstd")
            provenance_files[concept] = {
                "raw_filename": path.name,
                "sha256": self.sha256(path),
                "raw_schema": columns,
                "rows": int(pl.scan_parquet(target).select(pl.len()).collect().item()),
                "processed_filename": target.name,
            }
        provenance: dict[str, Any] = {
            "dataset": "Dunnhumby The Complete Journey",
            "source": source,
            "license_terms": license_terms,
            "placement_or_retrieval_time": datetime.now(UTC).isoformat(),
            "raw_directory": str(self.raw_dir.resolve()),
            "files": provenance_files,
            "canonical_mapping": {
                "transaction_data": ("Order/OrderLine; HOUSEHOLD_KEY is pseudonymous customer_id"),
                "discounts": "RETAIL_DISC and COUPON_DISC remain observed discount fields",
                "campaign_table+campaign_desc": "MarketingExposure/ActionExposure window",
                "coupon+coupon_redempt": (
                    "offer availability and redemption; redemption is not assignment"
                ),
            },
            "observed_fields": {
                concept: details["raw_schema"] for concept, details in provenance_files.items()
            },
            "derived_fields": [
                "canonical_customer_id",
                "canonical_order_id",
                "campaign_exposure_window",
                "post_exposure_30d_purchase",
            ],
        }
        (output / "provenance.json").write_text(json.dumps(provenance, indent=2), encoding="utf-8")
        return provenance

    def load(self) -> None:
        self.resolve_files()
        raise NotImplementedError("Use prepare() and benchmark only after actual schema audit")
