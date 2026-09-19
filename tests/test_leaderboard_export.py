"""The leaderboard's numbers must be right. Wilson intervals are checked against hand values, and the
committed data file must agree with itself (totals = sum of per-model counts = attempts listed)."""

import importlib.util
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("export_lb", ROOT / "scripts" / "export_leaderboard_data.py")
export_lb = importlib.util.module_from_spec(spec)
spec.loader.exec_module(export_lb)


def test_wilson_interval_hand_values():
    # 0 of 240: lower bound is exactly 0, upper is about z^2 / (n + z^2) = 3.84 / 243.84
    low, high = export_lb.wilson(0, 240)
    assert low == 0.0 and abs(high - 0.01575) < 1e-4
    # 6 of 20: standard Wilson result, roughly 14.5% to 51.9%
    low, high = export_lb.wilson(6, 20)
    assert abs(low - 0.1455) < 1e-3 and abs(high - 0.5190) < 1e-3
    assert export_lb.wilson(0, 0) == (0.0, 0.0)


def test_outcome_codes_follow_the_scoring_rules():
    f = export_lb.outcome_code
    assert f({"status": "ok", "resolved": True}) == 1
    assert f({"status": "ok", "resolved": False}) == 0
    assert f({"status": "timeout", "resolved": False}) == 2
    assert f({"status": "patch_apply_failed", "resolved": False}) == 3
    assert f({"status": "infra_error", "resolved": False}) is None  # excluded, never held against a model


def test_committed_data_file_is_self_consistent():
    data = json.loads((ROOT / "leaderboard" / "data" / "results.json").read_text())
    models, attempts = data["models"], data["attempts"]
    assert data["totals"]["attempts"] == len(attempts) == sum(m["attempts"] for m in models)
    assert data["totals"]["resolved"] == sum(m["resolved"] for m in models)
    assert data["totals"]["resolved"] == len([a for a in attempts if a[3] == 1])
    for mi, m in enumerate(models):
        mine = [a for a in attempts if a[0] == mi]
        assert len(mine) == m["attempts"]
        assert m["resolved"] + m["unresolved"] + m["timeouts"] + m["patch_apply_failed"] == m["attempts"]
        if m["attempts"]:
            assert m["ci_low"] <= m["rate"] <= m["ci_high"]
        else:
            assert m["status"] == "not_run" and m["rate"] is None
