from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from pathlib import Path

import polars as pl
import pytest

from commercial_twin.schemas import GeographicExposure
from commercial_twin.world_state import (
    CENSUS_REGIONS,
    CachedWorldStateProvider,
    normalize_us_geography,
)


def _write_cache(root: Path) -> None:
    (root / "raw/fred").mkdir(parents=True)
    (root / "raw/bls").mkdir(parents=True)
    (root / "processed").mkdir(parents=True)
    for series, value in (
        ("DSPIC96", 20_000.0),
        ("DRCCLACBS", 3.0),
        ("UMCSENT", 70.0),
    ):
        pl.DataFrame(
            {
                "observation_date": [datetime(2025, 1, 1), datetime(2025, 2, 1)],
                series: [value, value + 1],
            }
        ).write_csv(root / f"raw/fred/{series}.csv")
    bls = {
        "Results": {
            "series": [
                {
                    "data": [
                        {"year": "2025", "period": "M02", "value": "310.0"},
                        {"year": "2025", "period": "M01", "value": "309.0"},
                    ]
                }
            ]
        }
    }
    (root / "raw/bls/CUUR0000SAF11_1989_1998.json").write_text(json.dumps(bls))
    for geography, values in (("NUS", [3.0, 3.1]), ("TX", [2.5, 2.7])):
        pl.DataFrame(
            {
                "observation_period": [datetime(2025, 1, 6), datetime(2025, 1, 13)],
                "value": values,
            }
        ).write_csv(root / f"processed/eia_gas_{geography}.csv")


@pytest.fixture
def provider(tmp_path: Path) -> CachedWorldStateProvider:
    _write_cache(tmp_path)
    return CachedWorldStateProvider(tmp_path)


def test_all_states_normalize_and_have_a_region() -> None:
    assert len(CENSUS_REGIONS) == 51
    assert normalize_us_geography("California") == "CA"
    assert normalize_us_geography("illinois") == "IL"
    assert all(CENSUS_REGIONS[normalize_us_geography(code)] for code in CENSUS_REGIONS)


def test_point_in_time_availability_blocks_future_release(
    provider: CachedWorldStateProvider,
) -> None:
    before_release = provider.get_state(datetime(2025, 2, 28, tzinfo=UTC), "IL", "food_at_home")
    cpi = [
        signal for signal in before_release.signals if signal.signal_name == "category_cpi_level"
    ]
    assert not cpi
    after_release = provider.get_state(datetime(2025, 3, 2, tzinfo=UTC), "IL", "food_at_home")
    cpi = [signal for signal in after_release.signals if signal.signal_name == "category_cpi_level"]
    assert cpi[0].value == 309.0
    assert cpi[0].available_at is not None
    assert cpi[0].available_at <= after_release.as_of


def test_revised_series_are_rejected_for_strict_historical_backtest(
    provider: CachedWorldStateProvider,
) -> None:
    state = provider.get_state(datetime(2025, 5, 1, tzinfo=UTC), "CA", "food")
    assert "real_disposable_income:NOT_TESTABLE_ON_DOMINICKS" in state.unavailable_signals
    assert not any(signal.series_id == "DSPIC96" for signal in state.signals)


def test_geography_fallback_is_explicit(provider: CachedWorldStateProvider) -> None:
    provider.retrieved_at = datetime(2025, 4, 1, tzinfo=UTC)
    state = provider.get_state(datetime(2025, 4, 1, tzinfo=UTC), "Illinois", "food")
    sentiment = next(
        signal for signal in state.signals if signal.signal_name == "consumer_sentiment_level"
    )
    assert sentiment.requested_geography == "IL"
    assert sentiment.resolved_geography == "US"
    assert sentiment.geography_level == "NATIONAL"
    assert sentiment.fallback_level == "NATIONAL"
    assert sentiment.fallback_reason is not None


def test_real_state_series_and_national_fallback(provider: CachedWorldStateProvider) -> None:
    provider.retrieved_at = datetime(2025, 4, 1, tzinfo=UTC)
    texas = provider.get_state(datetime(2025, 4, 1, tzinfo=UTC), "TX", "food")
    illinois = provider.get_state(datetime(2025, 4, 1, tzinfo=UTC), "IL", "food")
    tx_gas = next(signal for signal in texas.signals if signal.signal_name == "gas_price_level")
    il_gas = next(signal for signal in illinois.signals if signal.signal_name == "gas_price_level")
    assert (tx_gas.resolved_geography, tx_gas.geography_level) == ("TX", "STATE")
    assert (il_gas.resolved_geography, il_gas.fallback_level) == ("US", "NATIONAL")


def test_exposure_aggregation_preserves_contributions_and_deduplicates_national(
    provider: CachedWorldStateProvider,
) -> None:
    provider.retrieved_at = datetime(2025, 4, 1, tzinfo=UTC)
    exposure = (
        GeographicExposure(geography="TX", weight=0.4),
        GeographicExposure(geography="CA", weight=0.6),
    )
    state = provider.get_exposure_state(datetime(2025, 4, 1, tzinfo=UTC), exposure, "food_at_home")
    sentiment = [
        signal for signal in state.signals if signal.signal_name == "consumer_sentiment_level"
    ]
    assert len(sentiment) == 1
    assert sentiment[0].resolved_geography == "US"
    gas = next(signal for signal in state.signals if signal.signal_name == "gas_price_level")
    assert float(gas.value) == pytest.approx(0.4 * 2.7 + 0.6 * 3.1)
    assert len(state.geographic_contributions["gas_price_level"]) == 2


def test_exposure_weights_must_sum_to_one(provider: CachedWorldStateProvider) -> None:
    with pytest.raises(ValueError, match="sum to 1"):
        provider.get_exposure_state(
            datetime.now(UTC),
            (GeographicExposure(geography="CA", weight=0.8),),
            "apparel",
        )


def test_signal_age_and_missing_category_are_explicit(
    provider: CachedWorldStateProvider,
) -> None:
    provider.retrieved_at = datetime(2025, 4, 1, tzinfo=UTC)
    state = provider.get_state(datetime(2025, 4, 1, tzinfo=UTC), "CA", "unknown")
    assert "category_cpi:NO_DEFENSIBLE_CATEGORY_MAPPING" in state.unavailable_signals
    assert all(signal.signal_age_days is not None for signal in state.signals)
    assert all(
        signal.available_at <= state.as_of for signal in state.signals if signal.available_at
    )


def test_category_mapping_never_relabels_food_cpi_as_apparel(
    provider: CachedWorldStateProvider,
) -> None:
    provider.retrieved_at = datetime(2025, 4, 1, tzinfo=UTC)
    state = provider.get_state(datetime(2025, 4, 1, tzinfo=UTC), "US", "apparel")
    assert "category_cpi:SERIES_NOT_CACHED:CUUR0000SAA" in state.unavailable_signals
    assert not any(signal.signal_name.startswith("category_cpi") for signal in state.signals)


def test_frequency_is_preserved(provider: CachedWorldStateProvider) -> None:
    provider.retrieved_at = datetime(2025, 5, 15, tzinfo=UTC)
    state = provider.get_state(datetime(2025, 5, 15, tzinfo=UTC), "US", "food")
    credit = next(signal for signal in state.signals if signal.signal_name == "credit_stress_level")
    assert credit.frequency == "QUARTERLY"
    assert credit.signal_age_days == pytest.approx(
        (state.as_of - credit.available_at).total_seconds() / 86_400
    )


def test_timezone_is_required(provider: CachedWorldStateProvider) -> None:
    with pytest.raises(ValueError, match="timezone-aware"):
        provider.get_state(datetime.now() - timedelta(days=1), "US", "food")
