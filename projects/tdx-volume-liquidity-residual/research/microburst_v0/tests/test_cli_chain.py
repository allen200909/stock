"""R6: in-process CLI chain (inspect-data -> compute-features -> join-vlr -> study) agrees with the one-command demo."""
from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from mbv.cli import event_study_kwargs, load_config, main

ROOT = Path(__file__).resolve().parents[1]
CFG = str(ROOT / "config" / "default.yaml")


@pytest.fixture(scope="module")
def demo_dirs(tmp_path_factory):
    tmp = tmp_path_factory.mktemp("cli")
    assert main(["demo", "--examples-dir", str(tmp / "ex"), "--outdir", str(tmp / "out"), "--config", CFG]) == 0
    return tmp


def test_cli_inspect_data_reports_contract_summary(demo_dirs, capsys):
    ex = demo_dirs / "ex"
    assert main(["inspect-data", "--minute", str(ex / "synthetic_minute_5m.csv"), "--daily",
                 str(ex / "synthetic_daily.csv"), "--config", CFG]) == 0
    info = json.loads(capsys.readouterr().out)
    assert info["status"] == "INSPECT_OK" and info["expected_slots_per_session"] == 48
    assert info["min_slots_observed"] == info["max_slots_observed"] == 48
    assert info["minute_rows"] == 6480 and info["daily_rows"] == 510


def test_cli_step_chain_matches_demo_outputs(demo_dirs):
    ex, out, step = demo_dirs / "ex", demo_dirs / "out", demo_dirs / "step"
    step.mkdir()
    assert main(["compute-features", "--minute", str(ex / "synthetic_minute_5m.csv"), "--config", CFG,
                 "--calendar", str(ex / "synthetic_calendar.csv"), "--out", str(step / "f.csv")]) == 0
    assert main(["join-vlr", "--daily", str(ex / "synthetic_daily.csv"), "--features", str(step / "f.csv"),
                 "--config", CFG, "--out", str(step / "j.csv")]) == 0
    assert main(["study", "--joined", str(step / "j.csv"), "--calendar", str(ex / "synthetic_calendar.csv"),
                 "--config", CFG, "--outdir", str(step / "study")]) == 0

    f_step = pd.read_csv(step / "f.csv")
    f_demo = pd.read_csv(out / "mbv_daily_features.csv")
    core = ["symbol", "trade_date", "feature_status", "burst_count", "burst_share", "peak_ratio",
            "burst_dominance", "burst_concentration", "valid_slot_coverage", "baseline_slot_coverage"]
    pd.testing.assert_frame_equal(f_step[core], f_demo[core], check_exact=False, rtol=1e-12)

    j_step = pd.read_csv(step / "j.csv")
    j_demo = pd.read_csv(out / "joined_vlr_mbv.csv")
    assert len(j_step) == len(j_demo) == 510
    b0 = [c for c in j_demo.columns if c.startswith("B0_")]
    pd.testing.assert_frame_equal(j_step[["symbol", "trade_date", *b0, "feature_status"]],
                                  j_demo[["symbol", "trade_date", *b0, "feature_status"]], check_exact=False,
                                  rtol=1e-12)
    md = (step / "study" / "study_report.md").read_text(encoding="utf-8")
    assert "SYNTHETIC_DEMO" in md and (step / "study" / "group_summary.csv").stat().st_size > 0
    np.testing.assert_array_equal(pd.read_csv(step / "study" / "group_summary.csv")["effective_events"],
                                  pd.read_csv(out / "group_summary.csv")["effective_events"])


def test_event_study_kwargs_reads_frozen_config_values():
    kw = event_study_kwargs(load_config(CFG))
    assert kw["board_policy"] == "strict" and kw["permutation_n"] == 1000
    assert kw["rvol_buckets"] == [0.0, 1.2, 1.5, 2.2, 3.0, 100.0]
    assert kw["mbv_share_cut"] == 0.15 and kw["mbv_dominance_cut"] == 0.25
    assert event_study_kwargs({})["board_policy"] == "strict"
