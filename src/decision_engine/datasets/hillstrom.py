"""Hillstrom RCT parser. No dates are invented for this cross-sectional experiment."""

from pathlib import Path

import polars as pl

from decision_engine.datasets.base import DatasetMetadata

CONTROL, MENS, WOMENS = "NO_EMAIL", "MENS_EMAIL", "WOMENS_EMAIL"
TREATMENTS = (CONTROL, MENS, WOMENS)
POST_TREATMENT_COLUMNS = frozenset(
    {"segment", "offer", "treatment", "visit", "conversion", "spend"}
)


class HillstromDataset:
    metadata = DatasetMetadata(
        "hillstrom", "mine-that-data-2008", randomized=True, known_propensity=True
    )

    def __init__(self, path: str | Path) -> None:
        self.path = Path(path)

    def load_rct(self) -> pl.DataFrame:
        if not self.path.exists():
            raise FileNotFoundError(f"Hillstrom dataset expected at {self.path}")
        raw = pl.read_csv(self.path, infer_schema_length=None)
        lookup = {column.strip().lower().replace(" ", "_"): column for column in raw.columns}
        required = {"segment", "spend", "conversion", "visit"}
        if missing := required - set(lookup):
            raise ValueError(f"Hillstrom file missing columns: {sorted(missing)}")
        frame = raw.rename({source: canonical for canonical, source in lookup.items()})
        frame = frame.with_row_index("row_id").with_columns(
            pl.col("segment")
            .cast(pl.String)
            .str.strip_chars()
            .str.to_lowercase()
            .replace_strict(
                {"no e-mail": CONTROL, "mens e-mail": MENS, "womens e-mail": WOMENS},
                default=None,
            )
            .alias("treatment")
        )
        if frame["treatment"].null_count():
            unknown = frame.filter(pl.col("treatment").is_null())["segment"].unique().to_list()
            raise ValueError(f"unrecognized treatments: {unknown}")
        if set(frame["treatment"].unique()) != set(TREATMENTS):
            raise ValueError("all three randomized treatment arms are required")
        return frame

    @staticmethod
    def feature_columns(frame: pl.DataFrame) -> list[str]:
        features = [
            column
            for column in frame.columns
            if column not in POST_TREATMENT_COLUMNS and column != "row_id"
        ]
        HillstromDataset.assert_pre_treatment_features(features)
        return features

    @staticmethod
    def assert_pre_treatment_features(features: list[str]) -> None:
        if forbidden := set(features) & POST_TREATMENT_COLUMNS:
            raise AssertionError(f"post-treatment leakage: {sorted(forbidden)}")
