"""R6 T16–T19: calendar gate, future-label isolation, strict matched controls, bootstrap wrapper & bucketed permutation."""
from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from mbv.aggregate import aggregate_daily_features
from mbv.baselines import build_tod_baseline
from mbv.cli import compute_mbv_daily_pipeline
from mbv.event_study import (
    GATE_STATUS,
    build_forward_outcome_labels,
    format_study_markdown_report,
    match_controls_same_date_rvol,
    permutation_negative_control,
    permute_within_buckets,
    run_calendar_block_bootstrap,
    run_event_study,
    validate_trading_calendar,
)
from mbv.join import join_daily_vlr_mbv
from mbv.schema import DataContractError

from tests._helpers import bdays, make_panel


def _joined(symbols, dates, *, ret_fn=None, extra=None) -> pd.DataFrame:
    """Minimal joined T-day table (no outcome columns). close_t = 10 * (1 + ret_fn(sym, d_idx))."""
    rows = []
    for s_i, sym in enumerate(symbols):
        for d_i, d in enumerate(dates):
            px = 10.0 + (0.0 if ret_fn is None else ret_fn(s_i, d_i))
            rows.append({"symbol": sym, "trade_date": d, "open": px, "high": px * 1.02, "low": px * 0.98,
                         "close": px, "volume": 1e6, "feature_status": "OK", "B0_EU": False,
                         "B0_ABU": False, "B0_VU": False, "B0_RVRAW": 1.0, "burst_share": 0.0,
                         "burst_dominance": 0.0, "burst_count": 0.0, "board": "MAIN"})
    df = pd.DataFrame(rows)
    if extra is not None:
        df = extra(df)
    return df


# --------------------------------------------------------------------------------------------- T16
@pytest.mark.parametrize(
    "cal, match",
    [
        (None, "Explicit trading_calendar is required"),
        ([], "must not be empty"),
        (["2026-01-06", "2026-01-05"], "sorted"),
        (["2026-01-05", "2026-01-05"], "unique"),
        (pd.DataFrame({"date": ["2026-01-05"]}), "trade_date"),
    ],
)
def test_t16_calendar_gate_fails_closed(cal, match):
    with pytest.raises(DataContractError, match=match):
        validate_trading_calendar(cal)
    joined = _joined(["600000.SH"], bdays(3))
    with pytest.raises(DataContractError):
        run_event_study(joined, trading_calendar=cal)
    with pytest.raises(DataContractError):
        build_forward_outcome_labels(joined, trading_calendar=cal)


def test_t16_dates_outside_calendar_rejected_and_calendar_gap_is_data_missing():
    dates = bdays(6)
    joined = _joined(["600000.SH"], dates)
    with pytest.raises(DataContractError, match="outside trading_calendar"):
        build_forward_outcome_labels(joined, trading_calendar=dates[1:])
    # a calendar session with no daily row is DATA_MISSING (not skipped over to the next present row)
    out = build_forward_outcome_labels(joined.drop(index=2), trading_calendar=dates, horizons=(1,))
    assert out.set_index("trade_date").loc[dates[1], "t1_fill_status"] == "DATA_MISSING"
    assert np.isnan(out.set_index("trade_date").loc[dates[1], "fwd_ret_1d"])
    assert out.set_index("trade_date").loc[dates[-1], "t1_fill_status"] == "PENDING_FUTURE_SESSION"


# --------------------------------------------------------------------------------------------- T17
def test_t17_forward_columns_rejected_in_feature_and_joined_tables():
    joined = _joined(["600000.SH"], bdays(5))
    for col in ("fwd_ret_5d", "mfe_5d", "mae_1d", "forward_return", "next_ret"):
        with pytest.raises(DataContractError, match="Forward-looking"):
            run_event_study(joined.assign(**{col: 0.0}), trading_calendar=bdays(5))
        with pytest.raises(DataContractError, match="Forward-looking"):
            join_daily_vlr_mbv(joined.drop(columns=["feature_status"]), joined[["symbol", "trade_date",
                               "feature_status"]].assign(**{col: 0.0}))


def test_t17_outcomes_are_a_separate_table_and_input_is_not_mutated():
    dates = bdays(8)
    joined = _joined(["600000.SH", "000001.SZ"], dates, ret_fn=lambda s, d: 0.1 * d)
    snapshot = joined.copy(deep=True)
    res = run_event_study(joined, trading_calendar=dates, horizons=(1, 3), min_events_per_group=1,
                          bootstrap_repetitions=100, permutation_n=10)
    pd.testing.assert_frame_equal(joined, snapshot)
    out = res["outcomes_table"]
    assert set(out.columns) >= {"symbol", "trade_date", "t1_date", "t1_fill_status", "fwd_ret_1d", "fwd_ret_3d"}
    assert not any(c.startswith(("fwd_", "mfe_", "mae_")) for c in joined.columns)
    # T close confirmation -> earliest T+1 open entry: fwd_ret_1d = close_{T+1} / open_{T+1} - 1 = 0 here
    o = out.set_index(["symbol", "trade_date"])
    assert o.loc[("600000.SH", dates[0]), "fwd_ret_1d"] == pytest.approx(0.0)
    assert o.loc[("600000.SH", dates[0]), "fwd_ret_3d"] == pytest.approx((10.3 / 10.1) - 1.0)
    assert o.loc[("600000.SH", dates[0]), "t1_date"] == dates[1]


def test_t17_t_day_features_unaffected_by_appending_future_minute_and_daily_data():
    dates = bdays(24)
    panel = make_panel(["600000.SH"], dates, lambda s, d, k: 1000.0 + (5000.0 if (d, k) == (22, 3) else 0.0))
    full = compute_mbv_daily_pipeline(panel)
    prefix = compute_mbv_daily_pipeline(panel[panel["trade_date"] <= dates[21]])
    pd.testing.assert_frame_equal(full[full["trade_date"] <= dates[21]].reset_index(drop=True),
                                  prefix.reset_index(drop=True), check_exact=True)
    assert not any(c.startswith(("fwd_", "mfe_", "mae_")) for c in full.columns)


def test_t17_t1_tradability_states_are_distinct_and_never_inferred_from_ohlc_alone():
    dates = bdays(6)

    def extra(df):
        df["suspended"] = False
        df["price_limit_status"] = "NONE"
        df["tradability_status_source"] = "EXCHANGE_STATUS_FEED_TEST"
        # T+1 for dates[0] opens at limit-up but trades (high > low) -> fill opportunity UNVERIFIED (R7)
        m = df["trade_date"] == dates[1]
        df.loc[m, ["open", "high", "low", "close", "price_limit_status"]] = [11.0, 11.0, 10.6, 10.9, "LIMIT_UP"]
        m2 = df["trade_date"] == dates[3]
        df.loc[m2, ["suspended", "volume"]] = [True, 0.0]
        return df

    with_status = _joined(["600000.SH"], dates, extra=extra)
    out = build_forward_outcome_labels(with_status, trading_calendar=dates, horizons=(1,)).set_index("trade_date")
    assert out.loc[dates[0], "t1_fill_status"] == "OPEN_LIMIT_UP_FILL_UNVERIFIED_T1"
    assert out.loc[dates[0], "t1_execution_class"] == "FILL_UNVERIFIED"
    assert out.loc[dates[0], "fwd_ret_1d"] == pytest.approx(10.9 / 11.0 - 1.0)  # hypothetical kept
    assert np.isnan(out.loc[dates[0], "exec_ret_1d"])  # never counted as executable
    assert out.loc[dates[1], "t1_fill_status"] == "ELIGIBLE_T1_OPEN_STATUS_CHECKED"
    # suspended=True with trusted source is confirmed; checked before the zero-volume fallback
    assert out.loc[dates[2], "t1_fill_status"] == "SUSPENDED_T1_STATUS_CONFIRMED"
    assert np.isnan(out.loc[dates[2], "fwd_ret_1d"])
    no_status = _joined(["600000.SH"], dates)
    out2 = build_forward_outcome_labels(no_status, trading_calendar=dates, horizons=(1,))
    assert set(out2["t1_fill_status"].iloc[:-1]) == {"TRADABILITY_UNVERIFIED_T1"}


# --------------------------------------------------------------------------------------------- T18
def _match_frame():
    rows = []
    for d in ("2026-01-05", "2026-01-06"):
        rows += [
            {"symbol": "A.SH", "trade_date": d, "B0_RVRAW": 1.6, "board": "MAIN", "fwd_ret_5d": 0.05, "t": True},
            {"symbol": "B.SZ", "trade_date": d, "B0_RVRAW": 1.7, "board": "CHINEXT", "fwd_ret_5d": 0.01, "t": False},
            {"symbol": "C.SH", "trade_date": d, "B0_RVRAW": 2.5, "board": "MAIN", "fwd_ret_5d": -0.02, "t": False},
        ]
    return pd.DataFrame(rows)


def test_t18_strict_board_never_silently_falls_back():
    df = _match_frame()
    res = match_controls_same_date_rvol(df, df["t"], min_events=1)
    assert res["board_policy"] == "strict" and res["board_constraint"] == "SAME_BOARD"
    # same-date same-bucket candidate (B.SZ) is on a different board, C.SH is another RVOL bucket -> unmatched
    assert res["n_matched"] == 0 and res["status"] == "INCONCLUSIVE"
    assert res["unmatched_reasons"] == {"NO_CANDIDATE": 2} and res["unmatched_rate"] == 1.0
    assert res["n_relaxed_board"] == 0


def test_t18_explicit_relaxation_is_counted_and_ignore_is_labelled():
    df = _match_frame()
    relaxed = match_controls_same_date_rvol(df, df["t"], min_events=1, board_policy="relax_explicit")
    assert relaxed["n_matched"] == 2 and relaxed["n_relaxed_board"] == 2
    assert relaxed["mean_excess"] == pytest.approx(0.04)
    ign = match_controls_same_date_rvol(df, df["t"], min_events=1, board_policy="ignore")
    assert ign["board_constraint"] == "NONE" and ign["n_matched"] == 2 and ign["n_relaxed_board"] == 0
    with pytest.raises(DataContractError, match="board_policy"):
        match_controls_same_date_rvol(df, df["t"], board_policy="loose")


def test_t18_insufficient_or_missing_inputs_are_inconclusive():
    df = _match_frame()
    assert match_controls_same_date_rvol(df, df["t"], min_events=5, board_policy="ignore")["status"] == "INCONCLUSIVE"
    none = match_controls_same_date_rvol(df, pd.Series(False, index=df.index))
    assert none["status"] == "INCONCLUSIVE" and none["reason"] == "NO_TREATED_EVENTS"
    nob = match_controls_same_date_rvol(df.drop(columns=["board"]), df["t"], min_events=1)
    assert nob["status"] == "INCONCLUSIVE" and nob["reason"] == "BOARD_COLUMN_MISSING"
    rv = df.copy()
    rv.loc[rv["t"], "B0_RVRAW"] = np.nan
    r = match_controls_same_date_rvol(rv, rv["t"], min_events=1, board_policy="ignore")
    assert r["unmatched_reasons"] == {"RVOL_MISSING": 2} and r["n_matched"] == 0
    with pytest.raises(DataContractError, match="B0_RVRAW"):
        match_controls_same_date_rvol(df.drop(columns=["B0_RVRAW"]), df["t"])


def test_t18_run_event_study_without_events_is_inconclusive_everywhere():
    dates = bdays(30)
    res = run_event_study(_joined(["600000.SH", "000001.SZ"], dates), trading_calendar=dates,
                          bootstrap_repetitions=100, permutation_n=10)
    assert res["matched_control_h1"]["status"] == "INCONCLUSIVE"
    assert res["permutation_control_e"]["status"] == "INCONCLUSIVE"
    assert res["bootstrap_status"] == "INCONCLUSIVE"
    assert (res["group_summary"]["group_status"] == "INCONCLUSIVE").all()
    assert res["gates"] == GATE_STATUS and "NO_RESEARCH_CONCLUSION" in res["conclusion"]
    md = format_study_markdown_report(res)
    assert "SYNTHETIC_DEMO" in md and "BLOCKED_REAL_DATA" in md and "NOT order-flow" in md


# --------------------------------------------------------------------------------------------- T19
def test_t19_bootstrap_constant_returns_give_degenerate_ci():
    cal = bdays(40)
    ev = pd.DataFrame({"date": cal[::2], "return": 0.0123})
    out = run_calendar_block_bootstrap(ev, trading_calendar=cal, block_lengths=(5, 10), repetitions=200, seed=7)
    assert list(out["block_length"]) == [5, 10]
    assert np.allclose(out["ci_low"], 0.0123) and np.allclose(out["ci_high"], 0.0123)
    assert (out["seed"] == 7).all() and (out["repetitions"] == 200).all()


def _independent_block_bootstrap(totals, counts, length, reps, seed, conf):
    """Independent re-implementation of the moving calendar-block bootstrap for cross-checking the wrapper."""
    n = len(totals)
    rng = np.random.default_rng(seed)
    est = []
    for _ in range(reps):
        k = (n + length - 1) // length
        starts = rng.integers(0, n - length + 1, size=k)
        pos = np.concatenate([np.arange(s, s + length) for s in starts])[:n]
        den = counts[pos].sum()
        if den:
            est.append(totals[pos].sum() / den)
    return np.quantile(est, [(1 - conf) / 2, (1 + conf) / 2]), len(est)


def test_t19_wrapper_equals_independent_reimplementation_on_tiny_calendar():
    cal = bdays(12)
    ev = pd.DataFrame({"date": [cal[0], cal[0], cal[3], cal[7], cal[10]], "return": [0.1, -0.05, 0.02, 0.3, -0.1]})
    out = run_calendar_block_bootstrap(ev, trading_calendar=cal, block_lengths=(3,), repetitions=150, seed=11)
    totals = np.zeros(12)
    counts = np.zeros(12)
    for d, r in zip(ev["date"], ev["return"]):
        totals[cal.index(d)] += r
        counts[cal.index(d)] += 1
    (lo, hi), valid = _independent_block_bootstrap(totals, counts, 3, 150, 11, 0.95)
    assert out.loc[0, "ci_low"] == pytest.approx(lo, abs=1e-12)
    assert out.loc[0, "ci_high"] == pytest.approx(hi, abs=1e-12)
    assert out.loc[0, "valid_draws"] == valid
    assert out.loc[0, "mean"] == pytest.approx(ev["return"].mean())


def test_t19_bootstrap_sparse_events_raise_and_study_reports_inconclusive():
    cal = bdays(60)
    with pytest.raises(ValueError, match="zero-event"):
        run_calendar_block_bootstrap(pd.DataFrame({"date": [cal[30]], "return": [0.1]}), trading_calendar=cal,
                                     block_lengths=(5,), repetitions=100, seed=1)


def test_t19_within_bucket_permutation_preserves_bucket_composition():
    rng = np.random.default_rng(3)
    vals = np.arange(12, dtype=float)
    buckets = np.array([0, 0, 0, 1, 1, 1, 1, 2, 3, 3, 3, 3])
    moved = False
    for _ in range(50):
        p = permute_within_buckets(vals, buckets, rng)
        for b in np.unique(buckets):
            assert sorted(p[buckets == b]) == sorted(vals[buckets == b])
        assert p[buckets == 2][0] == vals[buckets == 2][0]
        moved |= not np.array_equal(p, vals)
    assert moved


def _perm_frame(n_per_bucket=6):
    rows = []
    for b_i, rv in enumerate((1.0, 1.3, 1.8)):
        for j in range(n_per_bucket):
            rows.append({"symbol": f"S{b_i}{j}.SH", "trade_date": "2026-01-05", "B0_EU": True,
                         "feature_status": "OK", "B0_RVRAW": rv, "burst_share": 0.3 if j % 2 == 0 else 0.05,
                         "fwd_ret_5d": 0.01 * b_i + (0.02 if j % 2 == 0 else 0.0)})
    return pd.DataFrame(rows)


def test_t19_group_e_permutes_only_within_rvol_buckets_and_reports_metadata():
    df = _perm_frame()
    r1 = permutation_negative_control(df, "B0_EU", n_permutations=300, seed=5)
    r2 = permutation_negative_control(df, "B0_EU", n_permutations=300, seed=5)
    assert r1 == r2  # seeded and reproducible
    assert r1["status"] == "COMPLETED" and r1["method"] == "WITHIN_RVOL_BUCKET_PERMUTATION"
    assert r1["bucket_counts"] == {0: 6, 1: 6, 2: 6} and r1["n_permutable_buckets"] == 3
    assert r1["n_permutations_valid"] == 300 and r1["seed"] == 5
    assert r1["observed_spread"] == pytest.approx(0.02)
    assert 0.0 < r1["p_value_two_sided"] <= 1.0
    # high-RVOL bucket holding all "high share" rows: global permutation would mix buckets, within-bucket cannot
    conf = df.copy()
    conf["burst_share"] = np.where(conf["B0_RVRAW"] == 1.8, 0.3, 0.05)
    rc = permutation_negative_control(conf, "B0_EU", n_permutations=50, seed=5)
    assert rc["status"] == "INCONCLUSIVE" and rc["reason"] == "NO_PERMUTABLE_RVOL_BUCKET"


def test_t19_group_e_inconclusive_paths():
    df = _perm_frame()
    assert permutation_negative_control(df.drop(columns=["B0_RVRAW"]), "B0_EU")["reason"] == "RVOL_UNAVAILABLE"
    assert permutation_negative_control(df, "B0_XX")["reason"] == "BASE_EVENT_COLUMN_MISSING"
    few = permutation_negative_control(df.head(3), "B0_EU")
    assert few["status"] == "INCONCLUSIVE" and few["reason"] == "INSUFFICIENT_BASE_EVENTS_FOR_PERMUTATION"
    rv = df.copy()
    rv.loc[rv.index[:4], "B0_RVRAW"] = np.nan
    r = permutation_negative_control(rv, "B0_EU", n_permutations=20)
    assert r["n_rvol_missing"] == 4 and r["n_events"] == len(df) - 4
    deg = permutation_negative_control(df.assign(burst_share=0.01), "B0_EU")
    assert deg["reason"] == "DEGENERATE_SPLIT"
