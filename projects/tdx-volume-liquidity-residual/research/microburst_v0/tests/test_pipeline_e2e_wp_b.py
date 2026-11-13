"""WP-B: end-to-end engineering regressions — T01/T02/T03 full pipeline, T04/T05/T06 boundaries, pipeline input
contract, exchange-calendar baseline stepping."""
from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from _helpers import bdays, make_panel, slot_index
from mbv.baselines import build_tod_baseline
from mbv.cli import compute_mbv_daily_pipeline
from mbv.features import detect_bursts
from mbv.schema import DataContractError
from mbv.sessions import validate_minute_bars

SYMS = ["600000.SH", "000001.SZ", "300750.SZ"]


def _rich_vol(seed: int = 7):
    """Deterministic heterogeneous volume generator with injected bursts and a post-cutoff regime shift."""
    rng = np.random.default_rng(seed)
    noise = rng.uniform(0.85, 1.15, size=(len(SYMS), 40, 48))
    scale = {s: 1000.0 * (10 ** i) for i, s in enumerate(SYMS)}

    def vol(sym, d, k):
        i = SYMS.index(sym)
        v = scale[sym] * (1.0 + 0.4 * ((k - 24) / 24) ** 2) * noise[i, d, k]
        if d in (17, 19, 23, 27) and k in ((3 * i + d) % 48, (5 * i + 2 * d) % 48):
            v *= 4.0
        if d == 21 and sym == "300750.SZ" and k in (10, 11, 12, 13):
            v = 0.0  # zero-volume bars inside a session
        if d >= 26:
            v *= 30.0  # massive future regime shift
        return round(v, -1)

    def body(sym, d, k):
        return -0.12 if (d + k + SYMS.index(sym)) % 3 == 0 else 0.15

    return vol, body


# --------------------------------------------------------------------------------------------- T01 extended
def test_t01_current_future_and_other_slot_changes_do_not_move_baseline_at_t():
    dates = bdays(26)
    base = make_panel(["600000.SH"], dates, lambda s, d, k: 1000.0 + k)
    b0 = build_tod_baseline(base)
    slot_1455 = base["time_slot"].iloc[slot_index("14:55")]
    slot_0930 = base["time_slot"].iloc[slot_index("09:30")]

    # (a) shock day t's boundary slots and every future bar: all baselines on dates <= t are unchanged
    shocked = base.copy()
    on_t = (shocked["trade_date"] == dates[20]) & shocked["time_slot"].isin([slot_1455, slot_0930])
    shocked.loc[on_t, "volume"] = 9e9
    shocked.loc[shocked["trade_date"] > dates[20], "volume"] = 7e9
    b1 = build_tod_baseline(shocked)
    upto = b0["trade_date"] <= dates[20]
    bcols = ["symbol", "trade_date", "time_slot", "baseline", "history_positive_days", "baseline_status"]
    assert upto.sum() == 21 * 48
    pd.testing.assert_frame_equal(b0.loc[upto, bcols], b1.loc[upto, bcols], check_exact=True)
    # the raw volume passthrough on day t DID change (proves the shock was applied)
    assert (b1.loc[b1["trade_date"] == dates[20], "volume"] == 9e9).sum() == 2

    # (b) history shock confined to the 14:55 slot on 11 of the 20 window days moves ONLY that slot at t+1
    hist = base.copy()
    hmask = hist["trade_date"].between(dates[10], dates[20]) & (hist["time_slot"] == slot_1455)
    hist.loc[hmask, "volume"] = 50_000.0
    b2 = build_tod_baseline(hist)
    n0 = b0[b0["trade_date"] == dates[21]].set_index("time_slot")["baseline"]
    n2 = b2[b2["trade_date"] == dates[21]].set_index("time_slot")["baseline"]
    changed = set(n0.index[~np.isclose(n0.to_numpy(), n2.to_numpy())])
    assert changed == {slot_1455}
    assert n2.loc[slot_1455] == pytest.approx(50_000.0)
    # and no baseline on or before the first shocked day moved
    early = b0["trade_date"] <= dates[10]
    pd.testing.assert_frame_equal(b0.loc[early, bcols], b2.loc[early, bcols], check_exact=True)


# --------------------------------------------------------------------------------------------- T02 full pipeline
@pytest.mark.parametrize("use_calendar", [False, True])
def test_t02_multi_symbol_multi_date_end_to_end_prefix_invariance(use_calendar):
    dates = bdays(30)
    vol, body = _rich_vol()
    full = make_panel(SYMS, dates, vol, body_fn=body)
    cal = pd.DataFrame({"trade_date": dates}) if use_calendar else None
    daily_full = compute_mbv_daily_pipeline(full, trading_calendar=cal)
    bars_full = detect_bursts(full, build_tod_baseline(full, trading_calendar=cal))
    assert (daily_full["feature_status"] == "OK").sum() > 0
    assert daily_full.loc[daily_full["feature_status"] == "OK", "burst_count"].sum() > 0

    for cut in (15, 18, 21, 25):
        cutoff = dates[cut]
        trunc = full.loc[full["trade_date"] <= cutoff]
        cal_t = pd.DataFrame({"trade_date": dates[: cut + 1]}) if use_calendar else None
        daily_t = compute_mbv_daily_pipeline(trunc, trading_calendar=cal_t)
        prefix = daily_full.loc[daily_full["trade_date"] <= cutoff].reset_index(drop=True)
        pd.testing.assert_frame_equal(prefix, daily_t, check_exact=True)  # values, statuses, flags, dtypes

        bars_t = detect_bursts(trunc, build_tod_baseline(trunc, trading_calendar=cal_t))
        cols = ["symbol", "trade_date", "time_slot", "baseline", "rel_vol", "is_burst", "baseline_status",
                "history_positive_days", "burst_direction"]
        pd.testing.assert_frame_equal(
            bars_full.loc[bars_full["trade_date"] <= cutoff, cols].reset_index(drop=True),
            bars_t[cols].reset_index(drop=True),
            check_exact=True,
        )


# --------------------------------------------------------------------------------------------- T03 full pipeline
def test_t03_mixed_vs_single_symbol_full_pipeline_and_input_order_independence():
    dates = bdays(24)
    vol, body = _rich_vol(11)
    mixed = make_panel(SYMS, dates, vol, body_fn=body)
    res_mixed = compute_mbv_daily_pipeline(mixed)
    for sym in SYMS:
        alone = compute_mbv_daily_pipeline(mixed.loc[mixed["symbol"] == sym])
        pd.testing.assert_frame_equal(
            res_mixed.loc[res_mixed["symbol"] == sym].reset_index(drop=True), alone, check_exact=True
        )
    shuffled = mixed.sample(frac=1.0, random_state=3).reset_index(drop=True)
    pd.testing.assert_frame_equal(compute_mbv_daily_pipeline(shuffled), res_mixed, check_exact=True)


# --------------------------------------------------------------------------------------------- pipeline contract
@pytest.mark.parametrize(
    "mutate, match",
    [
        (lambda r: r.assign(ts=r["ts"].where(r.index != 5, r["ts"].iloc[5][:11] + "12:00:00")), "Lunch"),
        (lambda r: r.assign(ts=r["ts"].where(r.index != 5, r["ts"].iloc[5][:11] + "15:00:00")), "ambiguity"),
        (lambda r: r.assign(ts=r["ts"].where(r.index != 5, r["ts"].iloc[5][:11] + "09:31:00")), "grid"),
        (lambda r: r.assign(volume=r["volume"].where(r.index != 5, -5.0)), "non-negative"),
        (lambda r: r.assign(close=r["close"].where(r.index != 5, np.nan)), "NaN"),
        (lambda r: r.assign(high=r["high"].where(r.index != 5, 1.0)), "OHLC"),
        (lambda r: pd.concat([r, r.iloc[[5]]], ignore_index=True), "Duplicate"),
    ],
)
def test_pipeline_revalidates_input_and_rejects_unvalidated_minute_tables(mutate, match):
    raw = make_panel(["600000.SH"], bdays(16), lambda s, d, k: 1000.0, validate=False)
    compute_mbv_daily_pipeline(raw)  # raw-but-valid bar_start input is accepted
    with pytest.raises(DataContractError, match=match):
        compute_mbv_daily_pipeline(mutate(raw))


def test_pipeline_is_idempotent_on_validated_input_and_never_double_shifts_or_converts():
    dates = bdays(17)
    raw = make_panel(["600000.SH"], dates, lambda s, d, k: 4000.0 if (d == 16 and k == 2) else 1000.0, validate=False)
    once = validate_minute_bars(raw)
    twice = validate_minute_bars(once)
    pd.testing.assert_frame_equal(once, twice)
    a = compute_mbv_daily_pipeline(raw)
    b = compute_mbv_daily_pipeline(once)
    pd.testing.assert_frame_equal(a, b)
    # a lot_100 source normalized upstream is not multiplied again by the pipeline
    lots = raw.assign(volume=raw["volume"] / 100.0)
    norm = validate_minute_bars(lots, volume_unit="lot_100")
    pd.testing.assert_frame_equal(compute_mbv_daily_pipeline(norm), a)
    # bar_end source normalized upstream gives identical features
    shifted = raw.assign(ts=(pd.to_datetime(raw["ts"]) + pd.Timedelta(minutes=5)).dt.strftime("%Y-%m-%d %H:%M:%S"))
    pd.testing.assert_frame_equal(compute_mbv_daily_pipeline(validate_minute_bars(shifted, semantics="bar_end")), a)
    # but a raw bar_end table handed directly to the pipeline fails closed
    with pytest.raises(DataContractError):
        compute_mbv_daily_pipeline(shifted)
    assert a.set_index("trade_date").loc[dates[16], "burst_count"] == 1


# --------------------------------------------------------------------------------------------- T04/T05/T06 boundaries
def test_t04_lunch_break_not_missing_and_post_lunch_seasonality_not_a_fake_burst():
    dates = bdays(20)
    k1300 = slot_index("13:00")
    k0930 = slot_index("09:30")
    # every day the 09:30 and 13:00 slots trade 6x the rest: a TOD baseline must absorb this seasonality
    panel = make_panel(["600000.SH"], dates,
                       lambda s, d, k: 6000.0 if k in (k0930, k1300) else 1000.0)
    out = compute_mbv_daily_pipeline(panel).set_index("trade_date")
    last = out.loc[dates[19]]
    assert last["valid_slot_coverage"] == pytest.approx(1.0)  # lunch gap is not counted as missing
    assert last["observed_slots"] == 48
    assert last["burst_count"] == 0 and last["feature_status"] == "OK"
    times = panel["ts"].dt.time
    assert not ((times >= pd.Timestamp("11:30").time()) & (times < pd.Timestamp("13:00").time())).any()


def test_t04_t05_1min_session_boundaries_bar_start_and_bar_end():
    def one(ts):
        return pd.DataFrame({"symbol": ["600000.SH"], "ts": [ts], "open": [10.0], "high": [10.1],
                             "low": [9.9], "close": [10.0], "volume": [100.0]})

    for ok in ("09:30", "11:29", "13:00", "14:59"):
        validate_minute_bars(one(f"2026-01-05 {ok}:00"), frequency="1min")
    for bad in ("09:29", "11:30", "12:59", "15:00", "08:00"):
        with pytest.raises(DataContractError):
            validate_minute_bars(one(f"2026-01-05 {bad}:00"), frequency="1min")
    assert str(validate_minute_bars(one("2026-01-05 11:30:00"), semantics="bar_end", frequency="1min")
               ["time_slot"].iloc[0]) == "11:29:00"
    assert str(validate_minute_bars(one("2026-01-05 15:00:00"), semantics="bar_end", frequency="1min")
               ["time_slot"].iloc[0]) == "14:59:00"
    for bad_end in ("09:30", "13:00"):
        with pytest.raises(DataContractError, match="ambiguity"):
            validate_minute_bars(one(f"2026-01-05 {bad_end}:00"), semantics="bar_end", frequency="1min")
    # tz-aware UTC input converts to Asia/Shanghai bar_start (01:30Z == 09:30 CST)
    utc = one(pd.Timestamp("2026-01-05 01:30:00", tz="UTC"))
    assert str(validate_minute_bars(utc, frequency="1min")["time_slot"].iloc[0]) == "09:30:00"
    with pytest.raises(DataContractError):
        validate_minute_bars(one("2026-01-05 09:30:30"), frequency="1min")
    with pytest.raises(DataContractError, match="semantics"):
        validate_minute_bars(one("2026-01-05 09:30:00"), semantics="bar_mid", frequency="1min")


def test_t06_1min_pipeline_closing_auction_included_vs_excluded():
    dates = bdays(17)
    k1458 = slot_index("14:58", "1min")
    k1000 = slot_index("10:00", "1min")
    panel = make_panel(["600000.SH", "000001.SZ"], dates,
                       lambda s, d, k: 5000.0 if (d == 16 and k in (k1458, k1000)) else 1000.0,
                       frequency="1min")
    assert len(panel) == 2 * 17 * 240
    assert int(panel["closing_auction_window"].sum()) == 2 * 17 * 3
    cfg_in = {"data_contract": {"frequency": "1min", "exclude_closing_auction": False}}
    cfg_ex = {"data_contract": {"frequency": "1min", "exclude_closing_auction": True}}
    inc = compute_mbv_daily_pipeline(panel, config=cfg_in)
    exc = compute_mbv_daily_pipeline(panel, config=cfg_ex)
    d = inc[inc["trade_date"] == dates[16]].iloc[0]
    e = exc[exc["trade_date"] == dates[16]].iloc[0]
    assert (d["expected_slots"], e["expected_slots"]) == (240, 237)
    assert d["feature_status"] == e["feature_status"] == "OK"
    assert d["burst_count"] == 2 and e["burst_count"] == 1
    assert e["excluded_auction_volume"] == pytest.approx(5000.0 + 2 * 1000.0)
    assert e["minute_total_volume"] == d["minute_total_volume"]
    with pytest.raises(DataContractError, match="grid"):
        compute_mbv_daily_pipeline(panel)  # 1min data under default 5min config is rejected


# --------------------------------------------------------------------------------------------- calendar baseline
def test_exchange_calendar_stepping_counts_missing_sessions_in_the_20_session_window():
    cal = bdays(25)
    missing = set(cal[5:11])  # symbol absent on 6 exchange sessions (e.g. suspension with no rows)
    rows = []
    for d in cal:
        if d in missing:
            continue
        rows.append({"symbol": "600000.SH", "ts": f"{d} 09:30:00", "open": 10.0, "high": 10.2,
                     "low": 9.9, "close": 10.1, "volume": 200.0})
    df = validate_minute_bars(pd.DataFrame(rows))
    no_cal = build_tod_baseline(df).set_index("trade_date")
    with_cal = build_tod_baseline(df, trading_calendar=pd.DataFrame({"trade_date": cal})).set_index("trade_date")
    # without the calendar the window silently stretches over the gap: 18 positive "prior sessions"
    assert no_cal.loc[cal[24], "history_positive_days"] == 18
    assert no_cal.loc[cal[24], "baseline_status"] == "OK"
    # with the exchange calendar, sessions idx 4..23 contain 6 missing -> 14 < 15 -> INSUFFICIENT_HISTORY
    assert with_cal.loc[cal[24], "history_positive_days"] == 14
    assert with_cal.loc[cal[24], "baseline_status"] == "INSUFFICIENT_HISTORY"
    assert np.isnan(with_cal.loc[cal[24], "baseline"])
    with pytest.raises(DataContractError, match="outside trading_calendar"):
        build_tod_baseline(df, trading_calendar=cal[:20])
    with pytest.raises(DataContractError, match="sorted and unique"):
        build_tod_baseline(df, trading_calendar=list(reversed(cal)))
