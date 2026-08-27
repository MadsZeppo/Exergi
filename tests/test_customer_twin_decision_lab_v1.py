from __future__ import annotations

import ast
from pathlib import Path

import numpy as np
import pytest

from benchmarks.customer_twin_decision_lab_v1.oracle_world import WORLDS, OracleWorld
from benchmarks.customer_twin_decision_lab_v1.product_policy import PolicyState, choose


def test_oracle_is_not_imported_by_product_policy() -> None:
    path = Path("benchmarks/customer_twin_decision_lab_v1/product_policy.py")
    tree = ast.parse(path.read_text())
    imported = [node for node in ast.walk(tree) if isinstance(node, (ast.Import, ast.ImportFrom))]
    assert all("oracle_world" not in ast.unparse(node) for node in imported)


def test_world_is_deterministic_and_common_noise_is_shared() -> None:
    first = OracleWorld(WORLDS[1], 42, 5000, 12)
    second = OracleWorld(WORLDS[1], 42, 5000, 12)
    allocation = np.array([0.5, 0.5, 0.0])
    first_result = first.realize(3, allocation)
    second_result = second.realize(3, allocation)
    assert first_result[:2] == second_result[:2]
    assert np.array_equal(first_result[2], second_result[2])
    control = first.realize(3, np.array([1.0, 0.0, 0.0]))[0]
    treated = first.realize(3, allocation)[0]
    expected = int(first.customers * first.eligible_fraction) * 0.5 * first.effect(3)[1]
    assert treated - control == pytest.approx(expected)


def test_null_world_has_no_positive_action_effect() -> None:
    world = OracleWorld(WORLDS[0], 8, 5000, 12)
    assert np.max(world.effect(1)) == 0


def test_discount_revenue_trap_reconciles_direction() -> None:
    world = OracleWorld(WORLDS[2], 9, 5000, 12)
    assert world.revenue_effects[2] > 0
    assert world.effect(1)[2] < 0


def test_delayed_returns_reduce_discount_profit() -> None:
    delayed = OracleWorld(WORLDS[9], 11, 5000, 12)
    assert delayed.effect(1)[2] < delayed.effects[2]


def test_product_policy_accepts_only_observable_contract() -> None:
    observed = OracleWorld(WORLDS[1], 3, 5000, 12).observable(0, [])
    allocation = choose("twin", observed, PolicyState(), np.random.default_rng(1))
    assert np.allclose(allocation, [1 / 3, 1 / 3, 1 / 3])
    assert not hasattr(observed, "effects")


def test_all_fifteen_worlds_exist() -> None:
    assert len(WORLDS) == 15
    assert len({world.name for world in WORLDS}) == 15
