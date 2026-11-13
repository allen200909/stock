"""R7: study-mode / exchange-calendar policy (design decision §1, §3 'CONFIRMATORY_OOS not by string alone')."""
from __future__ import annotations

import hashlib
import json

import numpy as np
import pandas as pd
import pytest

from _helpers import bdays, make_panel
from mbv.calendar_policy import (
    CALENDAR_KIND_EXCHANGE,
    CALENDAR_KIND_NONE,
    CALENDAR_KIND_SYNTHETIC,
    assert_dates_in_preregistered_window,
    assert_feature_calendar_consistent,
    calendar_fingerprint,
    load_json_record,
    resolve_study_context,
    synthetic_calendar_provenance,
)
from mbv.cli import compute_mbv_daily_pipeline, main
from mbv.event_study import GATE_STATUS, run_event_study
from mbv.schema import DataContractError

CAL = bdays(40)


def _prov(cal=CAL, **over):
    p = {"kind": "EXCHANGE", "source": "SSE/SZSE official trading calendar (test fixture)", "verified": True,
         "verified_by": "independent reviewer (test)", "calendar_sha256": calendar_fingerprint(cal)}
    p.update(over)
    return p


def _prereg(tmp_path, cal=CAL, **over):
    doc = tmp_path / "prereg.md"
    doc.write_text("MBV V0.1 OOS pre-registration (test fixture)\n", encoding="utf-8")
    rec = {"registry_id": "MBV-OOS-TEST-001", "registered_on": "2025-12-01", "sample_start": cal[0],
           "sample_end": cal[-1], "data_source": "vendor X (test)", "document_path": "prereg.md",
           "document_sha256": hashlib.sha256(doc.read_bytes()).hexdigest()}
    rec.update(over)
    path = tmp_path / "prereg.json"
    path.write_text(json.dumps(rec), encoding="utf-8")
    return load_json_record(path)


def _joined(dates, cal_sha=None, symbols=("600000.SH",)):
    rows = []
    for sym in symbols:
        for d in dates:
            rows.append({"symbol": sym, "trade_date": d, "open": 10.0, "high": 10.2, "low": 9.8, "close": 10.0,
                         "volume": 1e6, "feature_status": "OK", "B0_EU": False, "B0_ABU": False, "B0_VU": False,
                         "B0_RVRAW": 1.0, "burst_share": 0.0, "burst_dominance": 0.0, "burst_count": 0.0,
                         "board": "MAIN"})
    df = pd.DataFrame(rows)
    if cal_sha is not None:
        df["calendar_sha256"] = cal_sha
    return df


_FAST = dict(horizons=(1,), min_events_per_group=1, bootstrap_repetitions=50, permutation_n=5)


# ------------------------------------------------------------------------------------------- SYNTHETIC_DEMO
def test_synthetic_calendar_is_labelled_synthetic_generated():
    ctx = resolve_study_context("SYNTHETIC_DEMO", CAL, calendar_provenance=synthetic_calendar_provenance(CAL, "gen"))
    assert ctx.calendar_kind == CALENDAR_KIND_SYNTHETIC and ctx.calendar_source == "gen"
    assert ctx.calendar_sha256 == calendar_fingerprint(CAL) and not ctx.is_formal
    assert ctx.research_grade == "SYNTHETIC_DEMO_ONLY"
    # even a provenance claiming EXCHANGE does not turn a synthetic run into an exchange-calendar run
    ctx2 = resolve_study_context("SYNTHETIC_DEMO", CAL, calendar_provenance=_prov())
    assert ctx2.calendar_kind == CALENDAR_KIND_SYNTHETIC


def test_synthetic_without_calendar_is_explicitly_symbol_observed_and_study_still_needs_calendar():
    ctx = resolve_study_context("SYNTHETIC_DEMO", None, require_calendar=False)
    assert ctx.calendar_kind == CALENDAR_KIND_NONE and ctx.calendar_sha256 is None
    with pytest.raises(DataContractError, match="Explicit trading_calendar is required"):
        resolve_study_context("SYNTHETIC_DEMO", None, require_calendar=True)
    with pytest.raises(DataContractError, match="does not match"):
        resolve_study_context("SYNTHETIC_DEMO", CAL, calendar_provenance={"calendar_sha256": "0" * 64})


# ------------------------------------------------------------------------------------ EXPLORATORY_REAL_DATA
@pytest.mark.parametrize(
    "cal, prov, match",
    [
        (None, None, "requires an explicit verified exchange trading calendar"),
        (CAL, None, "requires calendar provenance"),
        (CAL, _prov(kind="SYNTHETIC_GENERATED"), "kind='EXCHANGE'"),
        (CAL, _prov(verified=False), "verified exchange calendar"),
        (CAL, _prov(verified="true"), "verified exchange calendar"),  # string is not enough
        (CAL, _prov(verified_by=""), "verified_by"),
        (CAL, _prov(source="  "), "source"),
        (CAL, _prov(calendar_sha256="f" * 64), "does not match"),
        (CAL[:-1], _prov(), "does not match"),  # provenance bound to a different calendar
    ],
)
def test_exploratory_requires_verified_exchange_calendar(cal, prov, match):
    with pytest.raises(DataContractError, match=match):
        resolve_study_context("EXPLORATORY_REAL_DATA", cal, calendar_provenance=prov, require_calendar=False)


def test_exploratory_with_valid_provenance_and_gates_unchanged():
    ctx = resolve_study_context("EXPLORATORY_REAL_DATA", CAL, calendar_provenance=_prov())
    assert ctx.calendar_kind == CALENDAR_KIND_EXCHANGE and ctx.is_formal
    assert ctx.research_grade == "PROVISIONAL_RESEARCH"
    res = run_event_study(_joined(CAL, calendar_fingerprint(CAL)), trading_calendar=CAL,
                          study_mode="EXPLORATORY_REAL_DATA", calendar_provenance=_prov(), **_FAST)
    assert res["study_context"]["calendar_kind"] == "EXCHANGE"
    assert res["study_context"]["calendar_sha256"] == calendar_fingerprint(CAL)
    assert res["gates"] == GATE_STATUS == {"G1_REAL_MINUTE_DATA": "BLOCKED_REAL_DATA",
                                           "G2_TDX_B0_PARITY": "NOT_VERIFIED", "G3_REAL_EVENT_STUDY": "NOT_TESTED"}
    assert res["conclusion"].startswith("PROVISIONAL_RESEARCH_ONLY")


# ----------------------------------------------------------------------------------------- CONFIRMATORY_OOS
def test_confirmatory_string_alone_never_grants_label(tmp_path):
    with pytest.raises(DataContractError):
        resolve_study_context("CONFIRMATORY_OOS", CAL)
    with pytest.raises(DataContractError, match="pre-registration"):
        resolve_study_context("CONFIRMATORY_OOS", CAL, calendar_provenance=_prov())
    with pytest.raises(DataContractError):
        run_event_study(_joined(CAL, calendar_fingerprint(CAL)), trading_calendar=CAL,
                        study_mode="CONFIRMATORY_OOS", **_FAST)


def test_confirmatory_preregistration_failures(tmp_path):
    good = _prereg(tmp_path)
    with pytest.raises(DataContractError, match="missing fields"):
        resolve_study_context("CONFIRMATORY_OOS", CAL, calendar_provenance=_prov(),
                              preregistration={k: v for k, v in good.items() if k != "data_source"})
    with pytest.raises(DataContractError, match="document_sha256"):
        resolve_study_context("CONFIRMATORY_OOS", CAL, calendar_provenance=_prov(),
                              preregistration={**good, "document_sha256": "0" * 64})
    with pytest.raises(DataContractError, match="document not found"):
        resolve_study_context("CONFIRMATORY_OOS", CAL, calendar_provenance=_prov(),
                              preregistration={**good, "document_path": "missing.md"})
    with pytest.raises(DataContractError, match="strictly before"):
        resolve_study_context("CONFIRMATORY_OOS", CAL, calendar_provenance=_prov(),
                              preregistration={**good, "registered_on": CAL[0]})
    with pytest.raises(DataContractError, match="sample_start must be"):
        resolve_study_context("CONFIRMATORY_OOS", CAL, calendar_provenance=_prov(),
                              preregistration={**good, "sample_start": CAL[10], "sample_end": CAL[5]})
    with pytest.raises(DataContractError, match="inside the verified exchange calendar"):
        resolve_study_context("CONFIRMATORY_OOS", CAL, calendar_provenance=_prov(),
                              preregistration={**good, "sample_end": "2027-12-31"})
    with pytest.raises(DataContractError, match="Record file not found"):
        load_json_record(tmp_path / "nope.json")
    (tmp_path / "bad.json").write_text("{not json", encoding="utf-8")
    with pytest.raises(DataContractError, match="Invalid JSON"):
        load_json_record(tmp_path / "bad.json")
    (tmp_path / "list.json").write_text("[1]", encoding="utf-8")
    with pytest.raises(DataContractError, match="JSON object"):
        load_json_record(tmp_path / "list.json")


def test_confirmatory_valid_is_only_candidate_pending_review_and_window_enforced(tmp_path):
    window = CAL[20:]
    pre = _prereg(tmp_path, sample_start=window[0], sample_end=window[-1])
    ctx = resolve_study_context("CONFIRMATORY_OOS", CAL, calendar_provenance=_prov(), preregistration=pre)
    assert ctx.research_grade == "CONFIRMATORY_OOS_CANDIDATE_PENDING_INDEPENDENT_REVIEW"
    desc = ctx.describe()
    assert desc["preregistration"]["registry_id"] == "MBV-OOS-TEST-001"
    assert "document_path" not in desc["preregistration"]
    # feature pipeline: warm-up history before sample_start allowed, after sample_end rejected
    assert_dates_in_preregistered_window(ctx, pd.Series(CAL[:5]), allow_warmup=True)
    with pytest.raises(DataContractError, match="outside pre-registered window"):
        assert_dates_in_preregistered_window(ctx, pd.Series(CAL[:5]), allow_warmup=False)
    pre_short = _prereg(tmp_path, sample_start=CAL[20], sample_end=CAL[30])
    ctx_short = resolve_study_context("CONFIRMATORY_OOS", CAL, calendar_provenance=_prov(),
                                      preregistration=pre_short)
    with pytest.raises(DataContractError, match="outside pre-registered window"):
        assert_dates_in_preregistered_window(ctx_short, pd.Series(CAL[25:35]), allow_warmup=True)

    sha = calendar_fingerprint(CAL)
    with pytest.raises(DataContractError, match="outside pre-registered window"):
        run_event_study(_joined(CAL, sha), trading_calendar=CAL, study_mode="CONFIRMATORY_OOS",
                        calendar_provenance=_prov(), preregistration=pre, **_FAST)
    res = run_event_study(_joined(window, sha), trading_calendar=CAL, study_mode="CONFIRMATORY_OOS",
                          calendar_provenance=_prov(), preregistration=pre, **_FAST)
    assert res["research_grade"] == "CONFIRMATORY_OOS_CANDIDATE_PENDING_INDEPENDENT_REVIEW"
    assert res["gates"] == GATE_STATUS  # G1/G2/G3 never upgraded offline
    assert res["conclusion"].startswith("PROVISIONAL_RESEARCH_ONLY")


# --------------------------------------------------------------------------- calendar consistency (pipeline/study)
def test_pipeline_stamps_calendar_and_formal_pipeline_requires_calendar():
    dates = CAL[:22]
    panel = make_panel(["600000.SH"], dates, lambda s, d, k: 1000.0 + 3 * k)
    with pytest.raises(DataContractError, match="requires an explicit verified exchange trading calendar"):
        compute_mbv_daily_pipeline(panel, study_mode="EXPLORATORY_REAL_DATA")
    with pytest.raises(DataContractError, match="requires calendar provenance"):
        compute_mbv_daily_pipeline(panel, trading_calendar=dates, study_mode="EXPLORATORY_REAL_DATA")
    formal = compute_mbv_daily_pipeline(panel, trading_calendar=dates, study_mode="EXPLORATORY_REAL_DATA",
                                        calendar_provenance=_prov(dates))
    synth = compute_mbv_daily_pipeline(panel, trading_calendar=dates)
    assert set(formal["calendar_kind"]) == {"EXCHANGE"} and set(synth["calendar_kind"]) == {"SYNTHETIC_GENERATED"}
    assert set(formal["calendar_sha256"]) == set(synth["calendar_sha256"]) == {calendar_fingerprint(dates)}
    # 20-day window / >=15 positive-sample rule unchanged: formal == synthetic on identical calendar
    pd.testing.assert_frame_equal(formal.drop(columns=["calendar_kind"]), synth.drop(columns=["calendar_kind"]),
                                  check_exact=True)
    assert (formal["feature_status"].iloc[:15] != "OK").all()
    assert (formal["feature_status"].iloc[15:] == "OK").all()


def test_study_rejects_feature_calendar_mismatch_and_missing_stamps():
    sha_other = calendar_fingerprint(CAL[:-1])
    with pytest.raises(DataContractError, match="different calendar"):
        run_event_study(_joined(CAL, sha_other), trading_calendar=CAL, **_FAST)  # any mode
    with pytest.raises(DataContractError, match="stamped with calendar_sha256"):
        run_event_study(_joined(CAL), trading_calendar=CAL, study_mode="EXPLORATORY_REAL_DATA",
                        calendar_provenance=_prov(), **_FAST)
    partial = _joined(CAL, calendar_fingerprint(CAL))
    partial.loc[3, "calendar_sha256"] = np.nan
    with pytest.raises(DataContractError, match="lack calendar_sha256"):
        run_event_study(partial, trading_calendar=CAL, study_mode="EXPLORATORY_REAL_DATA",
                        calendar_provenance=_prov(), **_FAST)
    # rows without minute data do not need a stamp
    no_minute = _joined(CAL).assign(feature_status="MISSING_MINUTE_DATA")
    from mbv.calendar_policy import StudyContext
    ctx = resolve_study_context("EXPLORATORY_REAL_DATA", CAL, calendar_provenance=_prov())
    assert isinstance(ctx, StudyContext)
    assert_feature_calendar_consistent(ctx, no_minute)


def test_cli_formal_mode_requires_calendar_and_provenance(tmp_path):
    dates = CAL[:3]
    panel = make_panel(["600000.SH"], dates, lambda s, d, k: 1000.0)
    minute_csv = tmp_path / "m.csv"
    out = panel.copy()
    out["ts"] = out["ts"].astype(str)
    out[["symbol", "ts", "open", "high", "low", "close", "volume"]].to_csv(minute_csv, index=False)
    with pytest.raises(DataContractError, match="exchange trading calendar"):
        main(["compute-features", "--minute", str(minute_csv), "--out", str(tmp_path / "f.csv"),
              "--study-mode", "EXPLORATORY_REAL_DATA"])
    cal_csv = tmp_path / "cal.csv"
    pd.DataFrame({"trade_date": dates}).to_csv(cal_csv, index=False)
    with pytest.raises(DataContractError, match="requires calendar provenance"):
        main(["compute-features", "--minute", str(minute_csv), "--out", str(tmp_path / "f.csv"),
              "--study-mode", "EXPLORATORY_REAL_DATA", "--calendar", str(cal_csv)])
    prov = tmp_path / "prov.json"
    prov.write_text(json.dumps(_prov(dates)), encoding="utf-8")
    assert main(["compute-features", "--minute", str(minute_csv), "--out", str(tmp_path / "f.csv"),
                 "--study-mode", "EXPLORATORY_REAL_DATA", "--calendar", str(cal_csv),
                 "--calendar-provenance", str(prov)]) == 0
    f = pd.read_csv(tmp_path / "f.csv")
    assert set(f["calendar_kind"]) == {"EXCHANGE"} and set(f["calendar_sha256"]) == {calendar_fingerprint(dates)}
