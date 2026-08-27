from __future__ import annotations

from datetime import UTC, datetime

import pandas as pd

from commercial_twin.retailrocket_research import snapshot


def fixture_events() -> pd.DataFrame:
    values = [
        (1, "2020-01-01", "view"),
        (1, "2020-01-02", "addtocart"),
        (1, "2020-01-03", "view"),
        (1, "2020-01-05", "transaction"),
        (1, "2020-01-12", "view"),
    ]
    frame = pd.DataFrame(values, columns=["visitorid", "event_time", "event"])
    frame["event_time"] = pd.to_datetime(frame.event_time, utc=True)
    frame["timestamp"] = frame.event_time.astype("int64") // 1_000_000
    frame["itemid"] = range(len(frame))
    return frame


def test_state_has_no_future_and_targets_use_calendar_time() -> None:
    cutoff = datetime(2020, 1, 4, tzinfo=UTC)
    features, targets = snapshot(fixture_events(), cutoff)
    assert features.loc[0, "history_events"] == 3
    assert features.loc[0, "transaction_count"] == 0
    assert targets.loc[0, "transaction_any_1d"] == 0
    assert targets.loc[0, "transaction_any_7d"] == 1


def test_future_mutation_cannot_change_state() -> None:
    events = fixture_events()
    cutoff = datetime(2020, 1, 4, tzinfo=UTC)
    before, _ = snapshot(events, cutoff)
    events.loc[events.event_time > cutoff, "event"] = "transaction"
    after, _ = snapshot(events, cutoff)
    pd.testing.assert_frame_equal(before, after)
