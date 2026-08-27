from __future__ import annotations

import json

import pytest

from benchmarks.ecommerce_decision_layer_v7_1 import runner
from benchmarks.ecommerce_decision_layer_v7_1.packs import pack_payload, v71_pack_specs


def test_pack_manifests_and_seed_streams_are_disjoint() -> None:
    payloads = [pack_payload(pack) for pack in "OPQRSTU"]
    assert len({payload["spec_sha256"] for payload in payloads}) == len(payloads)
    specs = [spec for pack in "OPQRSTU" for spec in v71_pack_specs(pack)]
    assert len({spec.seed for spec in specs}) == len(specs)
    assert len({spec.world_id for spec in specs}) == len(specs)


def test_validation_opens_once_and_failed_validation_does_not_open_final(
    tmp_path, monkeypatch: pytest.MonkeyPatch
) -> None:
    development = tmp_path / "development.json"
    source = tmp_path / "source.json"
    lock = tmp_path / "opened.json"
    results = tmp_path / "results"
    report = tmp_path / "validation.md"
    development.write_text(
        json.dumps({"selected_model": "ridge_t_learner", "source_tree_sha256": "source"})
    )
    source.write_text(json.dumps({"source_tree_sha256": "source"}))
    monkeypatch.setattr(runner, "DEVELOPMENT_FREEZE", development)
    monkeypatch.setattr(runner, "SOURCE_FREEZE", source)
    monkeypatch.setattr(runner, "VALIDATION_LOCK", lock)
    monkeypatch.setattr(runner, "RESULTS", results)
    monkeypatch.setattr(runner, "VALIDATION_REPORT", report)
    monkeypatch.setattr(runner, "assert_clean_worktree", lambda: None)
    monkeypatch.setattr(runner, "_source_tree_hash", lambda: "source")
    monkeypatch.setattr(runner, "_evaluate", lambda packs, model: [])
    result = runner.run_validation()
    assert not result["overall_pass"]
    assert lock.exists()
    assert not (tmp_path / "pack_U_manifest.json").exists()
    with pytest.raises(RuntimeError, match="already been opened"):
        runner.run_validation()
