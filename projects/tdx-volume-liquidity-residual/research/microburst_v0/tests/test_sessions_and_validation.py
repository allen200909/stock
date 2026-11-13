"""T04, T05, T06, T07: A-share trading session geometry, timestamp semantics, slot counts & fail-closed validation."""
from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from mbv.adapters import load_synthetic_minute_data
from mbv.baselines import build_tod_baseline
from mbv.features import detect_bursts
from mbv.schema import DataContractError
from mbv.sessions import expected_session_slots, expected_slot_count, validate_minute_bars


def test_t04_lunch_break_and_off_hours_rejected_and_synthetic_has_zero_lunch_bars():
    """T04: 11:30-13:00 lunch break and off-hours (e.g. 08:00, 15:05) are rejected; synthetic loader has 0 lunch bars."""
    for bad_ts in ("2026-01-05 08:00:00", "2026-01-05 11:30:00", "2026-01-05 12:00:00", "2026-01-05 15:05:00"):
        bad_df = pd.DataFrame({
            "symbol": ["600000.SH"],
            "ts": [bad_ts],
            "open": [10.0],
            "high": [10.2],
            "low": [9.9],
            "close": [10.1],
            "volume": [1000.0],
        })
        with pytest.raises(DataContractError):
            validate_minute_bars(bad_df, semantics="bar_start", frequency="5min")

    syn = load_synthetic_minute_data(frequency="1min")
    t_vals = syn["ts"].dt.time
    lunch_count = ((t_vals >= pd.Timestamp("11:30").time()) & (t_vals < pd.Timestamp("13:00").time())).sum()
    assert lunch_count == 0


def test_t05_bar_start_vs_bar_end_normalization_and_ambiguity_rejection():
    """T05: bar_start and bar_end timestamps normalize identically; ambiguous boundaries raise DataContractError."""
    start_df = pd.DataFrame({
        "symbol": ["600000.SH"] * 4,
        "ts": [
            "2026-01-05 09:30:00",
            "2026-01-05 11:25:00",
            "2026-01-05 13:00:00",
            "2026-01-05 14:55:00",
        ],
        "open": [10.0, 10.1, 10.2, 10.3],
        "high": [10.2, 10.3, 10.4, 10.5],
        "low": [9.9, 10.0, 10.1, 10.2],
        "close": [10.1, 10.2, 10.3, 10.4],
        "volume": [1000.0, 1100.0, 1200.0, 1300.0],
    })
    end_df = start_df.copy()
    end_df["ts"] = [
        "2026-01-05 09:35:00",
        "2026-01-05 11:30:00",
        "2026-01-05 13:05:00",
        "2026-01-05 15:00:00",
    ]

    norm_start = validate_minute_bars(start_df, semantics="bar_start", frequency="5min")
    norm_end = validate_minute_bars(end_df, semantics="bar_end", frequency="5min")
    pd.testing.assert_series_equal(norm_start["ts"], norm_end["ts"])

    # Ambiguity 1: bar_end containing 09:30 must fail closed
    ambig_end = end_df.copy()
    ambig_end.loc[0, "ts"] = "2026-01-05 09:30:00"
    with pytest.raises(DataContractError, match="ambiguity"):
        validate_minute_bars(ambig_end, semantics="bar_end", frequency="5min")

    # Ambiguity 2: bar_start containing 15:00 must fail closed
    ambig_start = start_df.copy()
    ambig_start.loc[3, "ts"] = "2026-01-05 15:00:00"
    with pytest.raises(DataContractError, match="ambiguity"):
        validate_minute_bars(ambig_start, semantics="bar_start", frequency="5min")


def test_t06_1min_240_slots_and_5min_48_slots_and_closing_auction_flag():
    """T06: Normal session has exactly 240 (1min) and 48 (5min) slots; 14:57-15:00 closing auction flagged."""
    assert expected_slot_count("1min", exclude_closing_auction=False) == 240
    assert expected_slot_count("1min", exclude_closing_auction=True) == 237
    assert expected_slot_count("5min", exclude_closing_auction=False) == 48
    assert expected_slot_count("5min", exclude_closing_auction=True) == 47

    slots_1m = expected_session_slots("1min")
    df_1m = pd.DataFrame({
        "symbol": ["000001.SZ"] * len(slots_1m),
        "ts": [f"2026-01-05 {s.strftime('%H:%M:%S')}" for s in slots_1m],
        "open": [10.0] * len(slots_1m),
        "high": [10.1] * len(slots_1m),
        "low": [9.9] * len(slots_1m),
        "close": [10.05] * len(slots_1m),
        "volume": [100.0] * len(slots_1m),
    })
    val_1m = validate_minute_bars(df_1m, semantics="bar_start", frequency="1min", volume_unit="lot_100")
    assert len(val_1m) == 240
    assert int(val_1m["closing_auction_window"].sum()) == 3  # 14:57, 14:58, 14:59
    assert val_1m["volume"].iloc[0] == pytest.approx(10_000.0)  # lot_100 -> share


def test_t07_ohlc_bounds_negative_nan_inf_duplicates_and_zero_baseline_guard():
    """T07: Reject invalid OHLC, non-positive prices, negative/NaN/Inf volume, duplicate TS; handle H=L and zero baseline safely."""
    base_row = {
        "symbol": "600000.SH",
        "ts": "2026-01-05 09:30:00",
        "open": 10.0,
        "high": 10.5,
        "low": 9.8,
        "close": 10.3,
        "volume": 500.0,
    }

    # 1. Invalid OHLC (high < open)
    bad_ohlc = pd.DataFrame([{**base_row, "high": 9.9}])
    with pytest.raises(DataContractError, match="OHLC"):
        validate_minute_bars(bad_ohlc, frequency="5min")

    # 2. Non-positive price
    bad_price = pd.DataFrame([{**base_row, "low": 0.0, "open": 0.0, "close": 0.0, "high": 0.0}])
    with pytest.raises(DataContractError, match="positive"):
        validate_minute_bars(bad_price, frequency="5min")

    # 3. Negative, NaN, Inf volume
    for bad_v in (-1.0, np.nan, np.inf):
        bad_vol = pd.DataFrame([{**base_row, "volume": bad_v}])
        with pytest.raises(DataContractError):
            validate_minute_bars(bad_vol, frequency="5min")

    # 4. Duplicate (symbol, ts) rejected in both validate_minute_bars and build_tod_baseline (no silent summing!)
    dup_df = pd.DataFrame([base_row, base_row])
    with pytest.raises(DataContractError, match="Duplicate"):
        validate_minute_bars(dup_df, frequency="5min")
    with pytest.raises(DataContractError, match="Duplicate"):
        build_tod_baseline(dup_df)

    # 5. Flat H == L == O == C bar (e.g. locked board) has finite efficiency 0.0 and is NOT flagged as burst
    flat_df = validate_minute_bars(
        pd.DataFrame([{**base_row, "open": 10.0, "high": 10.0, "low": 10.0, "close": 10.0, "volume": 5000.0}]),
        frequency="5min",
    )
    valid_b = pd.DataFrame({
        "symbol": ["600000.SH"],
        "trade_date": ["2026-01-05"],
        "time_slot": [flat_df["time_slot"].iloc[0]],
        "baseline": [100.0],
    })
    det_flat = detect_bursts(flat_df, valid_b)
    assert det_flat["body_efficiency"].iloc[0] == pytest.approx(0.0)
    assert not bool(det_flat["is_burst"].iloc[0])

    # 6. Zero baseline -> BASELINE_INVALID, rel_vol is NaN (NEVER inf), is_burst is False!
    zero_b = valid_b.copy()
    zero_b["baseline"] = 0.0
    valid_bar = validate_minute_bars(pd.DataFrame([base_row]), frequency="5min")
    det_zero = detect_bursts(valid_bar, zero_b)
    assert np.isnan(det_zero["rel_vol"].iloc[0])
    assert not np.isinf(det_zero["rel_vol"].iloc[0])
    assert det_zero["baseline_status"].iloc[0] == "BASELINE_INVALID"
    assert not bool(det_zero["is_burst"].iloc[0])
