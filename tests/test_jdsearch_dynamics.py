from __future__ import annotations

from commercial_twin.jdsearch_dynamics import dynamics_row, snapshot_positions


def test_positions_leave_exactly_twenty_future_events() -> None:
    assert snapshot_positions(100, split="OFFICIAL_FINAL") == [80]
    assert snapshot_positions(39, split="TRAIN") == []


def test_dynamics_target_uses_events_strictly_after_cutoff() -> None:
    types = ["CLICK"] * 20 + ["ORD", "CART", "CLICK", "CLICK", "CLICK"] + ["CART"] * 15
    products = [str(index) for index in range(40)]
    queries = ["q"] * 40
    times = ["0"] + ["1"] * 40
    features, targets = dynamics_row(
        customer_key=1,
        position_index=0,
        cutoff=20,
        types=types,
        products=products,
        queries=queries,
        times=times,
    )
    assert features["ord_count_all"] == 0
    assert targets["next_event"] == 0
    assert targets["ord_any_5"] == 1
    assert targets["ord_count_5"] == 1
    assert targets["cart_count_5"] == 1


def test_future_mutation_cannot_change_state() -> None:
    types = ["CLICK"] * 40
    products = [str(index) for index in range(40)]
    queries = ["q"] * 40
    times = ["0"] + ["1"] * 40
    first, _ = dynamics_row(
        customer_key=1,
        position_index=0,
        cutoff=20,
        types=types,
        products=products,
        queries=queries,
        times=times,
    )
    types[20:] = ["ORD"] * 20
    second, _ = dynamics_row(
        customer_key=1,
        position_index=0,
        cutoff=20,
        types=types,
        products=products,
        queries=queries,
        times=times,
    )
    assert first == second
