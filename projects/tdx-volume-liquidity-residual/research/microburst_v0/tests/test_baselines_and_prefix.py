"""T01, T02, T03, T09: Past-only rolling TOD baseline causality, prefix invariance, symbol isolation & history gates."""
from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

import mbv.adapters as adapters_mod
from mbv.baselines import (
    build_tod_baseline,
    compute_rolling_tod_baseline,
    compute_rolling_tod_baseline_v2,
    compute_tod_baseline,
)
from mbv.cli import compute_mbv_daily_pipeline
from mbv.features import detect_bursts
from mbv.schema import DataContractError
from mbv.sessions import expected_session_slots, validate_minute_bars


def _make_full_5m_panel(symbols: list[str], dates: list[str], vol_fn) -> pd.DataFrame:
    slots = expected_session_slots("5min")
    rows = []
    for sym in symbols:
        for d_idx, d_str in enumerate(dates):
            for s_idx, slot_t in enumerate(slots):
                v = float(vol_fn(sym, d_idx, s_idx))
                rows.append({
                    "symbol": sym,
                    "ts": f"{d_str} {slot_t.strftime('%H:%M:%S')}",
                    "open": 10.00,
                    "high": 10.25,
                    "low": 9.95,
                    "close": 10.15,
                    "volume": v,
                })
    return validate_minute_bars(pd.DataFrame(rows), semantics="bar_start", frequency="5min")


def test_no_legacy_leaky_baseline_in_adapters():
    """Verify legacy all-sample `adapters.build_tod_baseline` has been completely removed."""
    assert not hasattr(adapters_mod, "build_tod_baseline")
    assert compute_rolling_tod_baseline is build_tod_baseline
    assert compute_rolling_tod_baseline_v2 is build_tod_baseline
    assert compute_tod_baseline is build_tod_baseline


def test_t01_current_and_future_volume_never_leak_into_baseline():
    """T01: Spiking current-day or future-day volume does not alter same-slot baseline at day t."""
    bdays = [d.strftime("%Y-%m-%d") for d in pd.bdate_range("2026-01-05", periods=25)]
    df_normal = _make_full_5m_panel(["600000.SH"], bdays, lambda _s, _d, _k: 1000.0)
    df_spiked = df_normal.copy()
    # Mutate day 20 (index 20) and future days 21..24 by 1000x
    spike_dates = set(bdays[20:])
    df_spiked.loc[df_spiked["trade_date"].isin(spike_dates), "volume"] = 1_000_000.0

    b_norm = build_tod_baseline(df_normal, lookback_days=20, min_history_days=15)
    b_spiked = build_tod_baseline(df_spiked, lookback_days=20, min_history_days=15)

    # On day index 20 (bdays[20]), baseline uses only days 0..19 -> must still be exactly 1000.0
    d20_norm = b_norm.loc[b_norm["trade_date"] == bdays[20], "baseline"].to_numpy()
    d20_spiked = b_spiked.loc[b_spiked["trade_date"] == bdays[20], "baseline"].to_numpy()
    assert np.allclose(d20_norm, 1000.0)
    assert np.allclose(d20_spiked, 1000.0)


def test_t02_end_to_end_prefix_invariance():
    """T02: Truncating the input at date T leaves all daily aggregated features on dates <= T identical."""
    bdays = [d.strftime("%Y-%m-%d") for d in pd.bdate_range("2026-01-05", periods=28)]

    def _vol(sym: str, d_idx: int, s_idx: int) -> float:
        if d_idx == 18 and s_idx in (2, 10):
            return 4500.0
        if d_idx >= 22:
            return 90_000.0  # Massive regime shift after cutoff T = bdays[20]
        return 1000.0 + 10.0 * s_idx

    full_df = _make_full_5m_panel(["600000.SH"], bdays, _vol)
    cutoff_date = bdays[20]
    trunc_df = full_df.loc[full_df["trade_date"] <= cutoff_date].copy()

    daily_full = compute_mbv_daily_pipeline(full_df)
    daily_trunc = compute_mbv_daily_pipeline(trunc_df)

    full_prefix = daily_full.loc[daily_full["trade_date"] <= cutoff_date].reset_index(drop=True)
    pd.testing.assert_frame_equal(full_prefix, daily_trunc, check_exact=False, rtol=1e-12, atol=1e-12)
    # Confirm day 18 (18 prior positive days >= 15) actually produced an OK burst observation
    d18 = daily_trunc.loc[daily_trunc["trade_date"] == bdays[18]].iloc[0]
    assert d18["feature_status"] == "OK"
    assert d18["burst_count"] == 2


def test_t03_cross_symbol_isolation_in_baseline_burst_and_aggregation():
    """T03: Mixing two symbols at identical timestamps never contaminates baselines or burst counts."""
    bdays = [d.strftime("%Y-%m-%d") for d in pd.bdate_range("2026-01-05", periods=22)]

    def _vol(sym: str, d_idx: int, s_idx: int) -> float:
        if sym == "600000.SH":
            return 4000.0 if (d_idx == 20 and s_idx == 0) else 1000.0
        # 000001.SZ trades at 100x higher normal volume (100,000), constant on day 20
        return 100_000.0

    mixed_df = _make_full_5m_panel(["600000.SH", "000001.SZ"], bdays, _vol)
    only_a = mixed_df.loc[mixed_df["symbol"] == "600000.SH"].copy()
    only_b = mixed_df.loc[mixed_df["symbol"] == "000001.SZ"].copy()

    res_mixed = compute_mbv_daily_pipeline(mixed_df)
    res_a = compute_mbv_daily_pipeline(only_a)
    res_b = compute_mbv_daily_pipeline(only_b)

    pd.testing.assert_frame_equal(
        res_mixed.loc[res_mixed["symbol"] == "600000.SH"].reset_index(drop=True),
        res_a.reset_index(drop=True),
    )
    pd.testing.assert_frame_equal(
        res_mixed.loc[res_mixed["symbol"] == "000001.SZ"].reset_index(drop=True),
        res_b.reset_index(drop=True),
    )

    d20_a = res_mixed.loc[(res_mixed["symbol"] == "600000.SH") & (res_mixed["trade_date"] == bdays[20])].iloc[0]
    d20_b = res_mixed.loc[(res_mixed["symbol"] == "000001.SZ") & (res_mixed["trade_date"] == bdays[20])].iloc[0]
    assert d20_a["burst_count"] == 1
    assert d20_b["burst_count"] == 0

    # Also verify passing a clock-time-only Series to multi-symbol detect_bursts fails closed
    clock_series = pd.Series([1000.0], index=[expected_session_slots("5min")[0]])
    with pytest.raises(DataContractError, match="Clock-time-only baseline Series is forbidden"):
        detect_bursts(mixed_df, clock_series)


def test_t09_15_to_19_positive_days_valid_and_zero_volumes_excluded():
    """T09: 15..19 positive prior days yield valid baseline; <15 positive days (even with zeros) -> INSUFFICIENT_HISTORY."""
    bdays = [d.strftime("%Y-%m-%d") for d in pd.bdate_range("2026-01-05", periods=25)]
    rows = []
    for idx, d_str in enumerate(bdays):
        rows.append({
            "symbol": "600000.SH",
            "ts": f"{d_str} 09:30:00",
            "open": 10.0,
            "high": 10.2,
            "low": 9.9,
            "close": 10.1,
            "volume": 200.0,
        })
    df = validate_minute_bars(pd.DataFrame(rows), frequency="5min")
    base = build_tod_baseline(df, lookback_days=20, min_history_days=15)

    # Index 0..14 have 0..14 prior days -> INSUFFICIENT_HISTORY & NaN
    for i in range(15):
        assert np.isnan(base.loc[i, "baseline"])
        assert base.loc[i, "baseline_status"] == "INSUFFICIENT_HISTORY"

    # Index 15..19 have 15..19 prior positive days -> MUST be valid (200.0), fixing R4 P0-1!
    for i in range(15, 25):
        assert base.loc[i, "baseline"] == pytest.approx(200.0)
        assert base.loc[i, "baseline_status"] == "OK"

    # Now construct R4 QA failure case: 15 zero-volume days followed by 6 positive days -> day 20 has only 5 positive prior days!
    rows_zero = []
    for idx, d_str in enumerate(bdays[:22]):
        vol = 0.0 if idx < 15 else 300.0
        rows_zero.append({
            "symbol": "600000.SH",
            "ts": f"{d_str} 09:30:00",
            "open": 10.0,
            "high": 10.2,
            "low": 9.9,
            "close": 10.1,
            "volume": vol,
        })
    df_z = validate_minute_bars(pd.DataFrame(rows_zero), frequency="5min")
    base_z = build_tod_baseline(df_z, lookback_days=20, min_history_days=15)
    # Day index 20 has 15 zeros + 5 positive days in prior 20 sessions -> only 5 positive -> INSUFFICIENT_HISTORY & NaN
    assert base_z.loc[20, "history_positive_days"] == 5
    assert np.isnan(base_z.loc[20, "baseline"])
    assert base_z.loc[20, "baseline_status"] == "INSUFFICIENT_HISTORY"

    # Furthermore, 20 positive days followed by 20 zero days -> on day 41, past-20 window has 0 positive days (NOT cumulative 20!)
    bdays_42 = [d.strftime("%Y-%m-%d") for d in pd.bdate_range("2026-01-05", periods=42)]
    rows_42 = []
    for idx, d_str in enumerate(bdays_42):
        vol = 500.0 if idx < 20 else (0.0 if idx < 40 else 500.0)
        rows_42.append({
            "symbol": "600000.SH",
            "ts": f"{d_str} 09:30:00",
            "open": 10.0,
            "high": 10.3,
            "low": 9.9,
            "close": 10.25,
            "volume": vol,
        })
    df_42 = validate_minute_bars(pd.DataFrame(rows_42), frequency="5min")
    det_42 = detect_bursts(df_42, lookback_days=20, min_history_days=15)
    day40_row = det_42.iloc[40]
    assert day40_row["history_positive_days"] == 0
    assert np.isnan(day40_row["rel_vol"])
    assert not bool(day40_row["is_burst"])
