"""R6 T20: one-command SYNTHETIC_DEMO end-to-end, non-empty outputs, labelled report, byte-reproducible manifest."""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pandas as pd
import pytest

ROOT = Path(__file__).resolve().parents[1]


def _run_demo(tmp: Path) -> tuple[subprocess.CompletedProcess, Path]:
    out = tmp / "out"
    proc = subprocess.run(
        [sys.executable, str(ROOT / "run_demo.py"), "demo", "--examples-dir", str(tmp / "ex"), "--outdir", str(out),
         "--config", str(ROOT / "config" / "default.yaml")],
        capture_output=True, text=True, timeout=600, cwd=str(tmp),
    )
    return proc, out


@pytest.fixture(scope="module")
def two_runs(tmp_path_factory):
    a = tmp_path_factory.mktemp("demo_a")
    b = tmp_path_factory.mktemp("demo_b")
    return _run_demo(a), _run_demo(b)


def test_t20_demo_exits_zero_with_non_empty_outputs(two_runs):
    (proc, out), _ = two_runs
    assert proc.returncode == 0, proc.stderr[-2000:]
    info = json.loads(proc.stdout)
    feats = pd.read_csv(out / "mbv_daily_features.csv")
    joined = pd.read_csv(out / "joined_vlr_mbv.csv")
    daily = pd.read_csv(out.parent / "ex" / "synthetic_daily.csv")
    assert len(feats) > 0 and feats["feature_status"].eq("OK").sum() > 0
    assert len(joined) == len(daily) == info["joined_rows"]
    assert not joined.duplicated(["symbol", "trade_date"]).any()
    # B0 events neither disappear nor duplicate through the join
    assert info["b0_event_counts"]["B0_EU"] == int(joined["B0_EU"].astype(bool).sum()) > 0
    assert set(joined["feature_status"]) >= {"OK", "MISSING_MINUTE_DATA"}
    assert not any(c.startswith(("fwd_", "mfe_", "mae_")) for c in feats.columns)
    assert not any(c.startswith(("fwd_", "mfe_", "mae_")) for c in joined.columns)
    for name in ("group_summary.csv", "forward_outcomes_labels.csv", "study_report.md", "run_manifest.json"):
        assert (out / name).stat().st_size > 0, name


def test_t20_report_is_labelled_synthetic_and_makes_no_alpha_claim(two_runs):
    (proc, out), _ = two_runs
    md = (out / "study_report.md").read_text(encoding="utf-8")
    assert "STUDY LABEL: `SYNTHETIC_DEMO`" in md
    assert "NOT order-flow" in md and "NO_RESEARCH_CONCLUSION" in md
    assert "BLOCKED_REAL_DATA" in md and "NOT_VERIFIED" in md and "NOT_TESTED" in md
    assert "WITHIN_RVOL_BUCKET_PERMUTATION" in md and "'board_policy': 'strict'" in md
    summary = pd.read_csv(out / "group_summary.csv")
    assert (summary["study_mode"] == "SYNTHETIC_DEMO").all()


def test_t20_two_runs_are_byte_reproducible(two_runs):
    (pa, oa), (pb, ob) = two_runs
    assert pa.returncode == 0 and pb.returncode == 0
    ma = json.loads((oa / "run_manifest.json").read_text())
    mb = json.loads((ob / "run_manifest.json").read_text())
    assert ma["outputs_sha256"] == mb["outputs_sha256"]
    assert ma["inputs_sha256"] == mb["inputs_sha256"]
    assert ma["params_hash"] == mb["params_hash"] and ma["summary"] == mb["summary"]
    assert ma["gates"]["G1_real_minute_data"] == "BLOCKED_REAL_DATA"
    assert ma["config"]["event_study"]["board_policy"] == "strict"
    assert set(ma["frozen_vlr_reference_sha256"]) == {"vlr.py", "validation.py", "inference.py"}
    assert (oa / "run_manifest.json").read_bytes() == (ob / "run_manifest.json").read_bytes()
