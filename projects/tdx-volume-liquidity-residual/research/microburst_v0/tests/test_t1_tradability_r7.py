"""R7: T+1 open-fill feasibility (design decision §2): status vs. order evidence, hypothetical vs. executable returns."""
from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from _helpers import bdays
from mbv.event_study import (
    EXECUTABLE_CLASSES,
    T1_STATUS_CLASS,
    build_forward_outcome_labels,
    format_study_markdown_report,
    run_event_study,
    validate_execution_evidence,
)
from mbv.join import join_daily_vlr_mbv
from mbv.schema import DataContractError

DATES = bdays(8)
SRC = "EXCHANGE_DAILY_STATUS_FEED (test fixture)"


def _panel(t1_override: dict | None = None, *, status=True, source=SRC, symbol="600000.SH") -> pd.DataFrame:
    """Flat 10.0 prices; DATES[1] (T+1 of DATES[0]) overridden by ``t1_override``. close of DATES[1]=10.5."""
    rows = []
    for d in DATES:
        rows.append({"symbol": symbol, "trade_date": d, "open": 10.0, "high": 10.6, "low": 9.9, "close": 10.0,
                     "volume": 1e6, "feature_status": "OK", "B0_EU": True, "B0_ABU": False, "B0_VU": False,
                     "B0_RVRAW": 1.6, "burst_share": 0.3, "burst_dominance": 0.5, "burst_count": 1.0,
                     "board": "MAIN"})
    df = pd.DataFrame(rows)
    df.loc[df["trade_date"] == DATES[1], "close"] = 10.5
    if status:
        df["suspended"] = False
        df["trading_restricted"] = False
        df["price_limit_status"] = "NONE"
    if source is not None:
        df["tradability_status_source"] = source
    if t1_override:
        m = df["trade_date"] == DATES[1]
        for k, v in t1_override.items():
            df.loc[m, k] = v
    return df


def _t0(out: pd.DataFrame) -> pd.Series:
    return out.set_index("trade_date").loc[DATES[0]]


def test_status_class_table_is_complete_and_executable_classes_fixed():
    assert set(T1_STATUS_CLASS.values()) == {"NO_DATA", "NOT_EXECUTABLE_CONFIRMED", "FILL_UNVERIFIED",
                                             "STATUS_CHECKED_EXECUTABLE", "CONFIRMED_FILLED"}
    assert EXECUTABLE_CLASSES == ("CONFIRMED_FILLED", "STATUS_CHECKED_EXECUTABLE")
    assert T1_STATUS_CLASS["OPEN_LIMIT_UP_FILL_UNVERIFIED_T1"] == "FILL_UNVERIFIED"
    assert T1_STATUS_CLASS["TRADABILITY_UNVERIFIED_T1"] == "FILL_UNVERIFIED"


def test_status_checked_eligible_has_exec_return_from_open_and_source_fields():
    r = _t0(build_forward_outcome_labels(_panel(), trading_calendar=DATES, horizons=(1,)))
    assert r["t1_fill_status"] == "ELIGIBLE_T1_OPEN_STATUS_CHECKED"
    assert r["t1_execution_class"] == "STATUS_CHECKED_EXECUTABLE"
    assert r["t1_status_source"] == SRC and pd.isna(r["t1_fill_evidence_source"])
    assert r["return_basis"] == "HYPOTHETICAL_T1_OPEN_PRICE"
    assert r["exec_entry_basis"] == "STATUS_CHECKED_T1_OPEN" and r["exec_entry_price"] == 10.0
    assert r["fwd_ret_1d"] == pytest.approx(0.05) and r["exec_ret_1d"] == pytest.approx(0.05)


@pytest.mark.parametrize("token", ["LIMIT_UP", "LOCKED_UP", "limit_up"])
def test_open_limit_up_is_fill_unverified_never_unfilled(token):
    ov = {"open": 10.6, "high": 10.6, "low": 10.2, "price_limit_status": token}
    r = _t0(build_forward_outcome_labels(_panel(ov), trading_calendar=DATES, horizons=(1,)))
    assert r["t1_fill_status"] == "OPEN_LIMIT_UP_FILL_UNVERIFIED_T1"
    assert r["t1_execution_class"] == "FILL_UNVERIFIED"
    assert "OPEN_AT_LIMIT_UP" in r["t1_risk_flags"] and r["t1_status_source"] == SRC
    assert r["fwd_ret_1d"] == pytest.approx(10.5 / 10.6 - 1.0)  # factor-research record kept
    assert np.isnan(r["exec_ret_1d"]) and np.isnan(r["exec_entry_price"])


def test_limit_up_boundary_open_below_high_is_status_checked():
    ov = {"open": 10.59, "high": 10.6, "low": 10.2, "price_limit_status": "LIMIT_UP"}
    r = _t0(build_forward_outcome_labels(_panel(ov), trading_calendar=DATES, horizons=(1,)))
    assert r["t1_fill_status"] == "ELIGIBLE_T1_OPEN_STATUS_CHECKED"


def test_one_word_limit_up_with_trusted_status_is_fill_unverified_and_flagged():
    ov = {"open": 10.6, "high": 10.6, "low": 10.6, "close": 10.6, "price_limit_status": "LOCKED_UP"}
    r = _t0(build_forward_outcome_labels(_panel(ov), trading_calendar=DATES, horizons=(1,)))
    assert r["t1_fill_status"] == "OPEN_LIMIT_UP_FILL_UNVERIFIED_T1"
    assert set(r["t1_risk_flags"].split("|")) >= {"ONE_WORD_LOCKED", "OPEN_AT_LIMIT_UP"}


@pytest.mark.parametrize("source, flag", [(None, "NO_TRUSTED_STATUS_SOURCE"), ("", "NO_TRUSTED_STATUS_SOURCE"),
                                          ("SYNTHETIC_GENERATOR", "UNTRUSTED_STATUS_SOURCE"),
                                          ("synthetic demo", "UNTRUSTED_STATUS_SOURCE")])
def test_untrusted_or_missing_source_is_tradability_unverified(source, flag):
    ov = {"open": 10.6, "high": 10.6, "low": 10.6, "price_limit_status": "LIMIT_UP", "suspended": True}
    r = _t0(build_forward_outcome_labels(_panel(ov, source=source), trading_calendar=DATES, horizons=(1,)))
    assert r["t1_fill_status"] == "TRADABILITY_UNVERIFIED_T1"
    assert r["t1_execution_class"] == "FILL_UNVERIFIED"
    flags = set(r["t1_risk_flags"].split("|"))
    assert {flag, "ONE_WORD_LOCKED", "OPEN_AT_LIMIT_UP", "SUSPENDED_FLAG_UNTRUSTED"} <= flags
    assert not np.isnan(r["fwd_ret_1d"]) and np.isnan(r["exec_ret_1d"])


def test_trusted_source_but_incomplete_status_is_unverified():
    df = _panel(status=False)
    r = _t0(build_forward_outcome_labels(df, trading_calendar=DATES, horizons=(1,)))
    assert r["t1_fill_status"] == "TRADABILITY_UNVERIFIED_T1" and "STATUS_INCOMPLETE" in r["t1_risk_flags"]


@pytest.mark.parametrize("ov, status, source", [
    ({"suspended": True, "volume": 0.0}, "SUSPENDED_T1_STATUS_CONFIRMED", SRC),
    ({"suspended": True}, "SUSPENDED_T1_STATUS_CONFIRMED", SRC),
    ({"trading_restricted": True}, "TRADING_RESTRICTED_T1_STATUS_CONFIRMED", SRC),
    ({"volume": 0.0}, "ZERO_VOLUME_T1", "DAILY_VOLUME"),
])
def test_confirmed_not_executable_states_have_no_returns(ov, status, source):
    r = _t0(build_forward_outcome_labels(_panel(ov), trading_calendar=DATES, horizons=(1, 3)))
    assert r["t1_fill_status"] == status and r["t1_execution_class"] == "NOT_EXECUTABLE_CONFIRMED"
    assert r["t1_status_source"] == source
    for c in ("fwd_ret_1d", "exec_ret_1d", "mfe_3d", "mae_3d", "exec_ret_3d"):
        assert np.isnan(r[c])


def test_zero_volume_without_any_status_columns_is_confirmed_by_daily_volume():
    r = _t0(build_forward_outcome_labels(_panel({"volume": 0.0}, status=False, source=None),
                                         trading_calendar=DATES, horizons=(1,)))
    assert r["t1_fill_status"] == "ZERO_VOLUME_T1" and r["t1_status_source"] == "DAILY_VOLUME"


def _ev(**over):
    row = {"symbol": "600000.SH", "entry_date": DATES[1], "evidence_type": "ORDER", "fill_status": "FILLED",
           "fill_price": 10.2, "evidence_source": "broker execution report #1 (test)"}
    row.update(over)
    return pd.DataFrame([row])


def test_order_evidence_filled_uses_fill_price_and_overrides_open_limit_up():
    ov = {"open": 10.6, "high": 10.6, "low": 10.2, "price_limit_status": "LIMIT_UP"}
    r = _t0(build_forward_outcome_labels(_panel(ov), trading_calendar=DATES, horizons=(1,),
                                         execution_evidence=_ev(fill_price=10.6)))
    assert r["t1_fill_status"] == "FILLED_T1_ORDER_EVIDENCE" and r["t1_execution_class"] == "CONFIRMED_FILLED"
    assert r["t1_status_source"] == "ORDER_EVIDENCE:ORDER"
    assert r["t1_fill_evidence_source"] == "broker execution report #1 (test)"
    assert r["exec_entry_basis"] == "ORDER_EVIDENCE_FILL_PRICE"
    assert r["exec_ret_1d"] == pytest.approx(10.5 / 10.6 - 1.0)
    r2 = _t0(build_forward_outcome_labels(_panel(), trading_calendar=DATES, horizons=(1,),
                                          execution_evidence=_ev()))
    assert r2["exec_ret_1d"] == pytest.approx(10.5 / 10.2 - 1.0)
    assert r2["fwd_ret_1d"] == pytest.approx(0.05)  # hypothetical stays on the open price


def test_order_book_evidence_not_filled_is_confirmed_unfilled_keeps_hypothetical_only():
    ov = {"open": 10.6, "high": 10.6, "low": 10.2, "price_limit_status": "LIMIT_UP"}
    r = _t0(build_forward_outcome_labels(
        _panel(ov), trading_calendar=DATES, horizons=(1,),
        execution_evidence=_ev(evidence_type="order_book", fill_status="NOT_FILLED", fill_price=np.nan)))
    assert r["t1_fill_status"] == "UNFILLED_T1_ORDER_EVIDENCE"
    assert r["t1_execution_class"] == "NOT_EXECUTABLE_CONFIRMED"
    assert r["t1_status_source"] == "ORDER_EVIDENCE:ORDER_BOOK"
    assert not np.isnan(r["fwd_ret_1d"]) and np.isnan(r["exec_ret_1d"])


@pytest.mark.parametrize("ev, match", [
    (pd.concat([_ev(), _ev()]), "Duplicate"),
    (_ev(evidence_source=" "), "evidence_source"),
    (_ev(evidence_source=np.nan), "evidence_source"),
    (_ev(fill_price=np.nan), "positive fill_price"),
    (_ev(fill_price=0.0), "positive fill_price"),
    (_ev(evidence_type="TRADE_TAPE"), "evidence_type"),
    (_ev(fill_status="PARTIAL"), "fill_status"),
    (_ev().drop(columns=["evidence_source"]), "missing columns"),
])
def test_execution_evidence_validation_fails_closed(ev, match):
    with pytest.raises(DataContractError, match=match):
        validate_execution_evidence(ev)


def test_evidence_unmatched_or_contradicting_confirmed_status_raises():
    with pytest.raises(DataContractError, match="does not match any available T"):
        build_forward_outcome_labels(_panel(), trading_calendar=DATES, horizons=(1,),
                                     execution_evidence=_ev(symbol="000001.SZ"))
    with pytest.raises(DataContractError, match="does not match any available T"):
        build_forward_outcome_labels(_panel(), trading_calendar=DATES, horizons=(1,),
                                     execution_evidence=_ev(entry_date=DATES[0]))  # no row has T+1 = DATES[0]
    for ov in ({"suspended": True}, {"trading_restricted": True}, {"volume": 0.0}):
        with pytest.raises(DataContractError, match="contradicts"):
            build_forward_outcome_labels(_panel(ov), trading_calendar=DATES, horizons=(1,),
                                         execution_evidence=_ev())
    assert validate_execution_evidence(None) == {}
    assert validate_execution_evidence(_ev().iloc[0:0]) == {}


def test_group_summary_exec_stats_exclude_fill_unverified_and_report_note():
    a = _panel({"open": 10.6, "high": 10.6, "low": 10.2, "price_limit_status": "LIMIT_UP"}, symbol="600000.SH")
    b = _panel(symbol="000001.SZ")
    joined = pd.concat([a, b], ignore_index=True)
    res = run_event_study(joined, trading_calendar=DATES, horizons=(1,), min_events_per_group=1,
                          bootstrap_repetitions=50, permutation_n=5)
    g = res["group_summary"].set_index("group").loc["A_VLR_EU_ONLY"]
    # 2 symbols x 7 rows with T+1; only symbol A day 0 is FILL_UNVERIFIED
    assert g["effective_events"] == 14 and g["fill_unverified_events"] == 1
    assert g["exec_effective_events"] == 13
    assert g["return_basis"] == "HYPOTHETICAL_T1_OPEN_PRICE"
    exec_vals = res["outcomes_table"]["exec_ret_1d"].dropna()
    assert g["exec_mean_return"] == pytest.approx(exec_vals.mean())
    assert res["t1_execution_class_counts"] == {"STATUS_CHECKED_EXECUTABLE": 13, "FILL_UNVERIFIED": 1,
                                                "NO_DATA": 2}
    md = format_study_markdown_report(res)
    assert "HYPOTHETICAL T+1 open-price returns" in md and "FILL_UNVERIFIED" in md
    assert "execution_class" in md and "Study Context" in md


def test_exec_ret_is_a_forbidden_feature_column():
    joined = _panel()
    with pytest.raises(DataContractError, match="Forward-looking"):
        run_event_study(joined.assign(exec_ret_1d=0.0), trading_calendar=DATES)
    with pytest.raises(DataContractError, match="Forward-looking"):
        join_daily_vlr_mbv(joined.drop(columns=["feature_status"]),
                           joined[["symbol", "trade_date", "feature_status"]].assign(exec_ret_5d=0.0))
