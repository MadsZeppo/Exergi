from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Protocol

import numpy as np
import polars as pl

from commercial_twin.schemas import GeographicExposure, WorldSignal, WorldState

CPI_CATEGORY_MAP = {
    "oatmeal": "CUUR0000SAF11",
    "food": "CUUR0000SAF11",
    "food_at_home": "CUUR0000SAF11",
    "apparel": "CUUR0000SAA",
    "home_furnishings": "CUUR0000SAH3",
}

US_STATE_CODES = {
    "ALABAMA": "AL",
    "ALASKA": "AK",
    "ARIZONA": "AZ",
    "ARKANSAS": "AR",
    "CALIFORNIA": "CA",
    "COLORADO": "CO",
    "CONNECTICUT": "CT",
    "DELAWARE": "DE",
    "FLORIDA": "FL",
    "GEORGIA": "GA",
    "HAWAII": "HI",
    "IDAHO": "ID",
    "ILLINOIS": "IL",
    "INDIANA": "IN",
    "IOWA": "IA",
    "KANSAS": "KS",
    "KENTUCKY": "KY",
    "LOUISIANA": "LA",
    "MAINE": "ME",
    "MARYLAND": "MD",
    "MASSACHUSETTS": "MA",
    "MICHIGAN": "MI",
    "MINNESOTA": "MN",
    "MISSISSIPPI": "MS",
    "MISSOURI": "MO",
    "MONTANA": "MT",
    "NEBRASKA": "NE",
    "NEVADA": "NV",
    "NEW HAMPSHIRE": "NH",
    "NEW JERSEY": "NJ",
    "NEW MEXICO": "NM",
    "NEW YORK": "NY",
    "NORTH CAROLINA": "NC",
    "NORTH DAKOTA": "ND",
    "OHIO": "OH",
    "OKLAHOMA": "OK",
    "OREGON": "OR",
    "PENNSYLVANIA": "PA",
    "RHODE ISLAND": "RI",
    "SOUTH CAROLINA": "SC",
    "SOUTH DAKOTA": "SD",
    "TENNESSEE": "TN",
    "TEXAS": "TX",
    "UTAH": "UT",
    "VERMONT": "VT",
    "VIRGINIA": "VA",
    "WASHINGTON": "WA",
    "WEST VIRGINIA": "WV",
    "WISCONSIN": "WI",
    "WYOMING": "WY",
    "DISTRICT OF COLUMBIA": "DC",
}

CENSUS_REGIONS = {
    **{code: "NORTHEAST" for code in ("CT", "ME", "MA", "NH", "RI", "VT", "NJ", "NY", "PA")},
    **{
        code: "MIDWEST"
        for code in ("IN", "IL", "MI", "OH", "WI", "IA", "KS", "MN", "MO", "NE", "ND", "SD")
    },
    **{
        code: "SOUTH"
        for code in (
            "DE",
            "DC",
            "FL",
            "GA",
            "MD",
            "NC",
            "SC",
            "VA",
            "WV",
            "AL",
            "KY",
            "MS",
            "TN",
            "AR",
            "LA",
            "OK",
            "TX",
        )
    },
    **{
        code: "WEST"
        for code in ("AZ", "CO", "ID", "MT", "NV", "NM", "UT", "WY", "AK", "CA", "HI", "OR", "WA")
    },
}


def normalize_us_geography(value: str) -> str:
    normalized = value.strip().upper().replace("_", " ")
    if normalized in {"US", "USA", "UNITED STATES", "COUNTRY", "NATIONAL"}:
        return "US"
    if normalized in CENSUS_REGIONS.values():
        return normalized
    if normalized in CENSUS_REGIONS:
        return normalized
    if normalized in US_STATE_CODES:
        return US_STATE_CODES[normalized]
    raise ValueError(f"unsupported US geography: {value}")


class WorldStateProvider(Protocol):
    def get_state(self, as_of: datetime, geography: str, commerce_category: str) -> WorldState: ...


@dataclass(frozen=True)
class SeriesDefinition:
    signal_family: str
    series_id: str
    source: str
    frequency: str
    geography: str
    geography_level: str
    path: Path
    value_column: str
    publication_lag_days: int
    vintage_safe_historical: bool
    vintage: str
    coverage_start: str
    coverage_end: str


def _month_available(year: int, month: int) -> datetime:
    """Conservative availability: first day of the second following month."""
    target = month + 2
    return datetime(year + (target - 1) // 12, (target - 1) % 12 + 1, 1, tzinfo=UTC)


class CachedWorldStateProvider:
    """Point-in-time provider over immutable locally cached official-source extracts."""

    def __init__(self, cache_root: str | Path = "data/world_state") -> None:
        root = Path(cache_root)
        self.retrieved_at = datetime.now(UTC)
        definitions = [
            SeriesDefinition(
                "real_disposable_income",
                "DSPIC96",
                "FRED / BEA",
                "MONTHLY",
                "US",
                "NATIONAL",
                root / "raw/fred/DSPIC96.csv",
                "DSPIC96",
                60,
                False,
                "LATEST_REVISED",
                "1959-01",
                "present",
            ),
            SeriesDefinition(
                "credit_stress",
                "DRCCLACBS",
                "FRED / Federal Reserve",
                "QUARTERLY",
                "US",
                "NATIONAL",
                root / "raw/fred/DRCCLACBS.csv",
                "DRCCLACBS",
                90,
                False,
                "LATEST_REVISED",
                "1991-Q1",
                "present",
            ),
            SeriesDefinition(
                "consumer_sentiment",
                "UMCSENT",
                "FRED / University of Michigan",
                "MONTHLY",
                "US",
                "NATIONAL",
                root / "raw/fred/UMCSENT.csv",
                "UMCSENT",
                60,
                False,
                "LATEST_FINAL_DELAYED",
                "1952-11",
                "present",
            ),
            SeriesDefinition(
                "category_cpi",
                "CUUR0000SAF11",
                "BLS",
                "MONTHLY",
                "US",
                "NATIONAL",
                root / "raw/bls/CUUR0000SAF11_1989_1998.json",
                "value",
                0,
                True,
                "NON_SEASONALLY_ADJUSTED_FINAL",
                "1989-01",
                "2026-08 cached windows",
            ),
            SeriesDefinition(
                "gas_price",
                "EMM_EPMR_PTE_NUS_DPG",
                "EIA",
                "WEEKLY",
                "US",
                "NATIONAL",
                root / "processed/eia_gas_NUS.csv",
                "value",
                3,
                False,
                "LATEST_REVISED",
                "1990-08-20",
                "present",
            ),
        ]
        for path in sorted((root / "processed").glob("eia_gas_*.csv")):
            source_geography = path.stem.removeprefix("eia_gas_")
            geography = (
                source_geography[1:]
                if source_geography.startswith("S") and source_geography[1:] in CENSUS_REGIONS
                else source_geography
            )
            if source_geography == "NUS" or geography not in CENSUS_REGIONS:
                continue
            definitions.append(
                SeriesDefinition(
                    "gas_price",
                    f"EMM_EPMR_PTE_{source_geography}_DPG",
                    "EIA",
                    "WEEKLY",
                    geography,
                    "STATE",
                    path,
                    "value",
                    3,
                    False,
                    "LATEST_REVISED",
                    "source-dependent",
                    "present",
                )
            )
        self.definitions = tuple(definitions)

    @staticmethod
    def category_series(commerce_category: str) -> str | None:
        return CPI_CATEGORY_MAP.get(commerce_category.lower())

    def coverage_report(self) -> list[dict[str, object]]:
        return [
            {
                "signal_family": item.signal_family,
                "series_id": item.series_id,
                "source": item.source,
                "frequency": item.frequency,
                "geography": item.geography,
                "geography_level": item.geography_level,
                "coverage_start": item.coverage_start,
                "coverage_end": item.coverage_end,
                "vintage": item.vintage,
                "vintage_safe_historical": item.vintage_safe_historical,
                "usable_on_dominicks": (
                    item.vintage_safe_historical and item.signal_family == "category_cpi"
                ),
            }
            for item in self.definitions
        ]

    def _load(self, definition: SeriesDefinition) -> pl.DataFrame:
        if definition.signal_family == "category_cpi":
            rows: list[dict[str, str]] = []
            for path in sorted(definition.path.parent.glob("CUUR0000SAF11_*.json")):
                payload = json.loads(path.read_text(encoding="utf-8"))
                rows.extend(payload["Results"]["series"][0]["data"])
            valid_rows = [
                row
                for row in rows
                if row["period"].startswith("M") and row["value"].replace(".", "", 1).isdigit()
            ]
            frame = pl.DataFrame(
                {
                    "observation_period": [
                        datetime(int(row["year"]), int(row["period"][1:]), 1, tzinfo=UTC)
                        for row in valid_rows
                    ],
                    "value": [float(row["value"]) for row in valid_rows],
                    "available_at": [
                        _month_available(int(row["year"]), int(row["period"][1:]))
                        for row in valid_rows
                    ],
                }
            )
            return frame.unique("observation_period", keep="last").sort("observation_period")
        frame = pl.read_csv(definition.path, try_parse_dates=True)
        date_name = (
            "observation_date" if "observation_date" in frame.columns else "observation_period"
        )
        frame = frame.select(
            pl.col(date_name).cast(pl.Datetime("us", "UTC")).alias("observation_period"),
            pl.col(definition.value_column).cast(pl.Float64, strict=False).alias("value"),
        ).drop_nulls()
        if definition.frequency in {"MONTHLY", "QUARTERLY"}:
            available = [
                _month_available(value.year, value.month)
                if definition.frequency == "MONTHLY"
                else value + timedelta(days=definition.publication_lag_days)
                for value in frame["observation_period"].to_list()
            ]
        else:
            available = [
                value + timedelta(days=definition.publication_lag_days)
                for value in frame["observation_period"].to_list()
            ]
        return frame.with_columns(pl.Series("available_at", available)).sort("observation_period")

    @staticmethod
    def _resolve(
        definitions: tuple[SeriesDefinition, ...], family: str, geography: str
    ) -> tuple[SeriesDefinition | None, str]:
        geography = normalize_us_geography(geography)
        candidates = [item for item in definitions if item.signal_family == family]
        exact = next((item for item in candidates if item.geography == geography), None)
        if exact is not None:
            return exact, exact.geography_level
        region = CENSUS_REGIONS.get(geography)
        regional = next((item for item in candidates if item.geography == region), None)
        if regional is not None:
            return regional, "REGION"
        national = next((item for item in candidates if item.geography_level == "NATIONAL"), None)
        return national, "NATIONAL" if national is not None else "NOT_AVAILABLE"

    def get_state(self, as_of: datetime, geography: str, commerce_category: str) -> WorldState:
        if as_of.tzinfo is None:
            raise ValueError("as_of must be timezone-aware")
        geography = normalize_us_geography(geography)
        historical = as_of < self.retrieved_at - timedelta(days=365)
        signals: list[WorldSignal] = []
        unavailable: list[str] = []
        for family in (
            "real_disposable_income",
            "credit_stress",
            "category_cpi",
            "consumer_sentiment",
            "gas_price",
        ):
            definition, fallback = self._resolve(self.definitions, family, geography)
            if definition is None or not definition.path.exists():
                unavailable.append(family)
                continue
            if family == "category_cpi":
                mapped_series = self.category_series(commerce_category)
                if mapped_series is None:
                    unavailable.append("category_cpi:NO_DEFENSIBLE_CATEGORY_MAPPING")
                    continue
                if mapped_series != definition.series_id:
                    unavailable.append(f"category_cpi:SERIES_NOT_CACHED:{mapped_series}")
                    continue
            if historical and not definition.vintage_safe_historical:
                unavailable.append(f"{family}:NOT_TESTABLE_ON_DOMINICKS")
                continue
            history = self._load(definition).filter(pl.col("available_at") <= as_of)
            if history.is_empty():
                unavailable.append(family)
                continue
            signals.extend(
                self._signals_from_history(history, definition, as_of, geography, fallback)
            )
        return WorldState(
            signals=tuple(signals),
            as_of=as_of,
            requested_geography=geography,
            commerce_category=commerce_category,
            unavailable_signals=tuple(unavailable),
        )

    def _signals_from_history(
        self,
        history: pl.DataFrame,
        definition: SeriesDefinition,
        as_of: datetime,
        requested_geography: str,
        fallback: str,
    ) -> list[WorldSignal]:
        values = history["value"].to_numpy()
        latest = history.row(-1, named=True)
        period_lag = 12 if definition.frequency == "MONTHLY" else 4
        previous = values[-2] if len(values) >= 2 else np.nan
        yoy = values[-period_lag - 1] if len(values) > period_lag else np.nan
        trailing = values[-min(len(values), period_lag * 3) :]
        standard = float(np.std(trailing, ddof=1)) if len(trailing) > 1 else 0.0
        transforms = {
            "level": float(values[-1]),
            "short_delta": float(values[-1] - previous) if np.isfinite(previous) else 0.0,
            "yoy_delta": float(values[-1] - yoy) if np.isfinite(yoy) else 0.0,
            "trailing_z": (
                float((values[-1] - np.mean(trailing)) / standard) if standard > 0 else 0.0
            ),
            "trend_deviation": float(values[-1] - np.mean(trailing)),
        }
        observation = latest["observation_period"]
        available = latest["available_at"]
        age = max((as_of - available).total_seconds() / 86400, 0.0)
        return [
            WorldSignal(
                signal_name=f"{definition.signal_family}_{transform}",
                value=value,
                observed_at=available,
                observation_period=observation,
                available_at=available,
                retrieved_at=self.retrieved_at,
                source=definition.source,
                series_id=definition.series_id,
                geography=definition.geography,
                resolved_geography=definition.geography,
                requested_geography=requested_geography,
                geography_level=definition.geography_level,
                fallback_level=fallback,
                fallback_reason=(
                    None
                    if definition.geography == requested_geography
                    else f"no official {requested_geography} series cached; used {fallback}"
                ),
                frequency=definition.frequency,
                vintage=definition.vintage,
                signal_age_days=age,
                provenance={"cache_path": str(definition.path)},
            )
            for transform, value in transforms.items()
        ]

    def feature_row(
        self, as_of: datetime, geography: str, commerce_category: str
    ) -> dict[str, float]:
        state = self.get_state(as_of, geography, commerce_category)
        return {
            signal.signal_name: float(signal.value)
            for signal in state.signals
            if isinstance(signal.value, (int, float))
        }

    def get_exposure_state(
        self,
        as_of: datetime,
        geographic_exposure: tuple[GeographicExposure, ...],
        commerce_category: str,
    ) -> WorldState:
        if not geographic_exposure:
            raise ValueError("geographic_exposure cannot be empty")
        total = sum(item.weight for item in geographic_exposure)
        if not np.isclose(total, 1.0, atol=1e-6):
            raise ValueError("geographic exposure weights must sum to 1")
        states = [
            self.get_state(as_of, item.geography, commerce_category) for item in geographic_exposure
        ]
        grouped: dict[str, list[tuple[GeographicExposure, WorldSignal]]] = {}
        unavailable: set[str] = set()
        for exposure, state in zip(geographic_exposure, states, strict=True):
            unavailable.update(state.unavailable_signals)
            for signal in state.signals:
                grouped.setdefault(signal.signal_name, []).append((exposure, signal))
        aggregated: list[WorldSignal] = []
        contributions: dict[str, tuple[dict[str, object], ...]] = {}
        for name, entries in grouped.items():
            resolved = {signal.resolved_geography for _, signal in entries}
            if resolved == {"US"}:
                representative = entries[0][1]
                aggregated.append(
                    representative.model_copy(
                        update={
                            "requested_geography": "WEIGHTED_US_EXPOSURE",
                            "fallback_reason": (
                                "national signal applied once; not duplicated by state"
                            ),
                        }
                    )
                )
            else:
                value = sum(item.weight * float(signal.value) for item, signal in entries)
                representative = entries[0][1]
                aggregated.append(
                    representative.model_copy(
                        update={
                            "value": value,
                            "geography": "WEIGHTED_US_EXPOSURE",
                            "resolved_geography": "WEIGHTED_US_EXPOSURE",
                            "requested_geography": "WEIGHTED_US_EXPOSURE",
                            "geography_level": "AGGREGATED",
                            "fallback_level": "MIXED",
                            "fallback_reason": "exposure-weighted from preserved contributions",
                        }
                    )
                )
            contributions[name] = tuple(
                {
                    "requested_geography": item.geography,
                    "weight": item.weight,
                    "weight_type": item.weight_type,
                    "resolved_geography": signal.resolved_geography,
                    "fallback_level": signal.fallback_level,
                    "value": signal.value,
                }
                for item, signal in entries
            )
        return WorldState(
            signals=tuple(aggregated),
            as_of=as_of,
            requested_geography="WEIGHTED_US_EXPOSURE",
            commerce_category=commerce_category,
            unavailable_signals=tuple(sorted(unavailable)),
            geographic_exposure=geographic_exposure,
            geographic_contributions=contributions,
        )


def get_current_world_state(
    geographic_exposure: str | tuple[GeographicExposure, ...],
    commerce_category: str,
    cache_root: str | Path = "data/world_state",
) -> WorldState:
    provider = CachedWorldStateProvider(cache_root)
    if isinstance(geographic_exposure, str):
        return provider.get_state(datetime.now(UTC), geographic_exposure, commerce_category)
    return provider.get_exposure_state(datetime.now(UTC), geographic_exposure, commerce_category)
