"""Point-in-time adapter for the public scikit-uplift X5 RetailHero distribution."""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from pathlib import Path

import polars as pl

EXPECTED_MD5 = {
    "uplift_train.csv.gz": "2720bbb659daa9e0989b2777b6a42d19",
    "clients.csv.gz": "b9cdeb2806b732771de03e819b3354c5",
    "purchases.csv.gz": "48d2de13428e24e8b61d66fef02957a8",
}


@dataclass(frozen=True)
class X5Provenance:
    distributor: str
    treatment_description: str
    random_assignment_proven: bool
    evidence_label: str
    missing_original_files: tuple[str, ...]


class X5RetailHeroAdapter:
    def __init__(self, root: Path) -> None:
        self.root = root

    def audit(self) -> X5Provenance:
        for name, expected in EXPECTED_MD5.items():
            path = self.root / name
            if not path.exists():
                raise FileNotFoundError(path)
            checksum = hashlib.md5()  # noqa: S324 - publisher checksum, not security
            with path.open("rb") as source:
                for chunk in iter(lambda: source.read(1024 * 1024), b""):
                    checksum.update(chunk)
            digest = checksum.hexdigest()
            if digest != expected:
                raise ValueError(f"publisher checksum mismatch: {name}")
        return X5Provenance(
            distributor="scikit-uplift public S3 distribution",
            treatment_description="binary flag for performed customer communication",
            random_assignment_proven=False,
            evidence_label="EXPERIMENTAL_RANDOMIZATION_NOT_PROVEN",
            missing_original_files=("products.csv", "uplift_test.csv"),
        )

    def materialize_features(self, output: Path) -> pl.DataFrame:
        """Build customer features exclusively from documented pre-communication purchases."""
        self.audit()
        if output.exists():
            return pl.read_parquet(output)
        train = pl.read_csv(self.root / "uplift_train.csv.gz")
        clients = pl.read_csv(self.root / "clients.csv.gz").with_columns(
            pl.col("first_issue_date").str.to_datetime(strict=False),
            pl.col("first_redeem_date").str.to_datetime(strict=False),
        )
        eligible = train.lazy().select("client_id")
        purchases = (
            pl.scan_csv(self.root / "purchases.csv.gz")
            .join(eligible, on="client_id", how="inner")
            .with_columns(
                pl.col("transaction_datetime").str.to_datetime(strict=False).alias("event_time")
            )
        )
        cutoff = purchases.select(pl.col("event_time").max()).collect().item()
        transactions = purchases.group_by(["client_id", "transaction_id"]).agg(
            pl.col("event_time").min().alias("event_time"),
            pl.col("purchase_sum").first().alias("purchase_sum"),
            pl.col("store_id").first().alias("store_id"),
            pl.col("product_quantity").sum().alias("basket_quantity"),
            (pl.col("regular_points_spent").sum() + pl.col("express_points_spent").sum()).alias(
                "points_spent"
            ),
        )
        customer = (
            transactions.group_by("client_id")
            .agg(
                ((pl.lit(cutoff) - pl.col("event_time").max()).dt.total_days()).alias(
                    "recency_days"
                ),
                pl.len().alias("frequency"),
                pl.col("purchase_sum").sum().alias("monetary"),
                pl.col("purchase_sum").mean().alias("average_basket_value"),
                pl.col("basket_quantity").mean().alias("average_basket_quantity"),
                pl.col("event_time").min().alias("first_purchase"),
                pl.col("event_time").max().alias("last_purchase"),
                pl.col("store_id").n_unique().alias("unique_stores"),
                (pl.col("points_spent") > 0).mean().alias("discount_exposure_rate"),
                pl.col("purchase_sum")
                .filter(pl.col("event_time") >= pl.lit(cutoff).dt.offset_by("-30d"))
                .sum()
                .alias("spend_30d"),
                pl.col("purchase_sum")
                .filter(pl.col("event_time") >= pl.lit(cutoff).dt.offset_by("-90d"))
                .sum()
                .alias("spend_90d"),
            )
            .with_columns(
                (
                    (pl.col("last_purchase") - pl.col("first_purchase")).dt.total_days()
                    / pl.max_horizontal(pl.col("frequency") - 1, pl.lit(1))
                ).alias("purchase_cadence_days"),
                ((pl.lit(cutoff) - pl.col("first_purchase")).dt.total_days()).alias(
                    "customer_tenure_days"
                ),
                (pl.col("spend_30d") - pl.col("spend_90d") / 3).alias("spend_trend"),
            )
        )
        products = purchases.group_by("client_id").agg(
            pl.col("product_id").n_unique().alias("unique_products"),
            pl.len().alias("product_lines"),
        )
        frame = (
            train.lazy()
            .join(clients.lazy(), on="client_id", how="left")
            .join(customer, on="client_id", how="left")
            .join(products, on="client_id", how="left")
            .with_columns(
                pl.col("gender").fill_null("U"),
                pl.col("age").fill_null(pl.col("age").median()),
                (
                    pl.col("unique_products")
                    / pl.max_horizontal(pl.col("product_lines"), pl.lit(1))
                ).alias("product_diversity"),
            )
            .collect()
        )
        output.parent.mkdir(parents=True, exist_ok=True)
        frame.write_parquet(output)
        return frame
