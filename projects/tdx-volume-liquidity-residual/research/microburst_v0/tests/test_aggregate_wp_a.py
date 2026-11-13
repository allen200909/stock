"""WP-A: public daily aggregation contract — schema, gates (T08), slot denominators (T06), math (T10), T11."""
from __future__ import annotations

from datetime import time

import numpy as np
import pandas as pd
import pytest

from _helpers import bdays, burst_rows, make_panel, slot_index
from mbv.aggregate import AGG_OUTPUT_COLS, AGG_REQUIRED_INPUT_COLS, aggregate_daily_features
from mbv.cli import compute_mbv_daily_pipeline
from mbv.features import detect_bursts
from mbv.schema import DataContractError

D = "2026-02-02"


def _agg(df, **kw):
    return aggregate_daily_features(df, **kw)


# --------------------------------------------------------------------------------------------- schema / empty
def test_public_aggregate_full_schema_types_and_unique_keys():
    dates = bdays(22)
    panel = make_panel(["600000.SH", "000001.SZ"], dates, lambda s, d, k: 1000.0 + 7 * k)
    out = compute_mbv_daily_pipeline(panel)
    assert list(out.columns) == list(AGG_OUTPUT_COLS) + ["calendar_kind", "calendar_sha256"]
    # R7: synthetic run without calendar is explicitly labelled, never silently treated as exchange calendar
    assert (out["calendar_kind"] == "NONE_SYMBOL_OBSERVED_DATES").all()
    assert out["calendar_sha256"].isna().all()
    assert len(out) == 2 * 22
    assert not out.duplicated(["symbol", "trade_date"]).any()
    assert out["symbol"].notna().all() and out["trade_date"].notna().all()
    assert out["burst_count"].dtype == np.float64
    assert out["single_burst_flag"].dtype == bool
    assert out["expected_slots"].dtype == np.int64
    assert (out["expected_slots"] == 48).all()
    pd.testing.assert_frame_equal(out, out.sort_values(["symbol", "trade_date"]).reset_index(drop=True))
    num = out.select_dtypes(include=[float]).to_numpy()
    assert not np.isinf(num).any()


def test_empty_input_returns_fixed_schema_and_bad_inputs_fail_closed():
    empty = pd.DataFrame({c: [] for c in AGG_REQUIRED_INPUT_COLS})
    out = _agg(empty)
    assert len(out) == 0
    assert list(out.columns) == list(AGG_OUTPUT_COLS)
    with pytest.raises(DataContractError):
        _agg(None)
    with pytest.raises(DataContractError, match="missing required columns"):
        _agg(pd.DataFrame({"symbol": ["A"], "trade_date": [D]}))
    with pytest.raises(DataContractError):
        _agg(burst_rows("A.SH", D, {}), frequency="15min")


@pytest.mark.parametrize(
    "mutate, match",
    [
        (lambda f: pd.concat([f, f.iloc[[0]]], ignore_index=True), "Duplicate"),
        (lambda f: f.assign(rel_vol=f["rel_vol"].where(f.index != 3, np.inf)), "inf"),
        (lambda f: f.assign(baseline=f["baseline"].where(f.index != 3, -np.inf)), "inf"),
        (lambda f: f.assign(volume=f["volume"].where(f.index != 3, -1.0)), "non-negative"),
        (lambda f: f.assign(body_efficiency=f["body_efficiency"].where(f.index != 3, np.nan)), "NaN"),
        (lambda f: f.assign(symbol=f["symbol"].where(f.index != 3, None)), "symbol"),
        (lambda f: f.assign(trade_date=f["trade_date"].where(f.index != 3, None)), "trade_date"),
        (lambda f: f.assign(time_slot=[time(12, 0)] + list(f["time_slot"].iloc[1:])), "Off-grid"),
        (lambda f: f.assign(time_slot=["25:99"] + list(f["time_slot"].iloc[1:])), "time_slot"),
        (lambda f: f.assign(is_burst=f.index == 3, baseline=f["baseline"].where(f.index != 3, np.nan)), "baseline"),
        (lambda f: f.assign(is_burst=f["is_burst"].astype(object).where(f.index != 3, None)), "is_burst"),
    ],
)
def test_t07_t14_aggregation_input_contract_rejections(mutate, match):
    good = burst_rows("600000.SH", D, {})
    _agg(good)  # sanity: the unmutated frame is accepted
    with pytest.raises(DataContractError, match=match):
        _agg(mutate(good))


# --------------------------------------------------------------------------------------------- T08 coverage gates
def test_t08_coverage_gate_95pct_and_na_plus_status():
    ok46 = _agg(burst_rows("A.SH", D, {}, drop_slots=(0, 1)))  # 46/48 = 0.958
    assert ok46.loc[0, "feature_status"] == "OK"
    assert ok46.loc[0, "valid_slot_coverage"] == pytest.approx(46 / 48)
    assert ok46.loc[0, "burst_count"] == 0 and ok46.loc[0, "burst_share"] == 0.0

    low = _agg(burst_rows("A.SH", D, {5: {"volume": 900.0, "body_efficiency": 0.5, "is_burst": True}},
                          drop_slots=(0, 1, 2)))  # 45/48 = 0.9375
    r = low.iloc[0]
    assert r["feature_status"] == "LOW_COVERAGE"
    assert r["valid_slot_coverage"] == pytest.approx(45 / 48)
    for c in ("burst_count", "burst_share", "burst_dominance", "burst_concentration", "peak_ratio",
              "burst_direction_agreement"):
        assert np.isnan(r[c]), c  # never filled with 0
    assert not r["single_burst_flag"]
    assert r["burst_regime"] == "UNAVAILABLE"
    assert r["minute_total_volume"] == pytest.approx(45 * 100.0 + 800.0)

    # Baseline coverage below 95% (minute bars complete) -> INSUFFICIENT_HISTORY, distinct from LOW_COVERAGE
    nob = {k: {"baseline": np.nan, "rel_vol": np.nan} for k in (0, 1, 2)}
    ih = _agg(burst_rows("A.SH", D, nob)).iloc[0]
    assert ih["feature_status"] == "INSUFFICIENT_HISTORY"
    assert ih["valid_slot_coverage"] == pytest.approx(1.0)
    assert ih["baseline_slot_coverage"] == pytest.approx(45 / 48)
    assert np.isnan(ih["burst_count"]) and np.isnan(ih["burst_share"])


def test_t08_status_priority_no_volume_over_low_coverage_over_insufficient_history():
    zero_low = burst_rows("A.SH", D, {k: {"volume": 0.0} for k in range(48)}, drop_slots=(0, 1, 2, 3))
    assert _agg(zero_low).loc[0, "feature_status"] == "NO_VOLUME"
    low_and_nohist = burst_rows("A.SH", D, {k: {"baseline": np.nan, "rel_vol": np.nan} for k in range(10, 20)},
                                drop_slots=(0, 1, 2, 3))
    assert _agg(low_and_nohist).loc[0, "feature_status"] == "LOW_COVERAGE"
    nohist = burst_rows("A.SH", D, {k: {"baseline": np.nan, "rel_vol": np.nan} for k in range(10, 20)})
    assert _agg(nohist).loc[0, "feature_status"] == "INSUFFICIENT_HISTORY"


def test_t08_pipeline_low_coverage_and_insufficient_history_days_are_na_with_status():
    dates = bdays(22)
    # day 20 of 000001.SZ is missing 4 slots -> LOW_COVERAGE; days 0..14 lack history -> INSUFFICIENT_HISTORY
    panel = make_panel(["000001.SZ"], dates, lambda s, d, k: 1000.0,
                       skip_fn=lambda s, d, k: d == 20 and k in (10, 11, 12, 13))
    out = compute_mbv_daily_pipeline(panel).set_index("trade_date")
    assert out.loc[dates[20], "feature_status"] == "LOW_COVERAGE"
    assert np.isnan(out.loc[dates[20], "burst_count"])
    assert (out.loc[dates[:15], "feature_status"] == "INSUFFICIENT_HISTORY").all()
    assert out.loc[dates[:15], "burst_share"].isna().all()
    assert out.loc[dates[21], "feature_status"] == "OK"
    assert out.loc[dates[21], "burst_count"] == 0


# --------------------------------------------------------------------------------------------- T06 denominators
def test_t06_5min_closing_auction_exclusion_adjusts_denominator_and_keeps_reconciliation():
    k1455 = slot_index("14:55")
    spec = {k1455: {"volume": 900.0, "body_efficiency": 0.6, "is_burst": True},
            4: {"volume": 400.0, "body_efficiency": 0.4, "is_burst": True}}
    rows = burst_rows("A.SH", D, spec)
    daily = pd.DataFrame({"symbol": ["A.SH"], "trade_date": [D], "volume": [rows["volume"].sum()]})

    incl = _agg(rows, frequency="5min", exclude_closing_auction=False, daily_ref=daily).iloc[0]
    excl = _agg(rows, frequency="5min", exclude_closing_auction=True, daily_ref=daily).iloc[0]
    assert incl["expected_slots"] == 48 and incl["observed_slots"] == 48
    assert excl["expected_slots"] == 47 and excl["observed_slots"] == 47
    assert excl["valid_slot_coverage"] == pytest.approx(1.0)
    assert incl["burst_count"] == 2 and excl["burst_count"] == 1  # 14:55 burst removed from feature universe
    assert excl["excluded_auction_volume"] == pytest.approx(900.0)
    assert incl["excluded_auction_volume"] == 0.0
    # reconciliation always against the full minute session volume
    assert excl["minute_total_volume"] == pytest.approx(rows["volume"].sum())
    assert excl["vol_recon_status"] == "RECONCILED_OK" and excl["vol_recon_error"] == pytest.approx(0.0)
    assert excl["burst_share"] == pytest.approx(400.0 / (rows["volume"].sum() - 900.0))
    # a session that simply lacks 14:55: 47/47 when excluded, 47/48 (still >= 95%) when included
    no_auction = burst_rows("A.SH", D, {}, drop_slots=(k1455,))
    assert _agg(no_auction, exclude_closing_auction=True).loc[0, "valid_slot_coverage"] == pytest.approx(1.0)
    assert _agg(no_auction).loc[0, "valid_slot_coverage"] == pytest.approx(47 / 48)


def test_t06_1min_240_and_237_denominators_in_aggregation():
    rows = burst_rows("A.SH", D, {}, frequency="1min")
    assert len(rows) == 240
    a = _agg(rows, frequency="1min").iloc[0]
    b = _agg(rows, frequency="1min", exclude_closing_auction=True).iloc[0]
    assert a["expected_slots"] == 240 and a["observed_slots"] == 240
    assert b["expected_slots"] == 237 and b["observed_slots"] == 237
    assert b["excluded_auction_volume"] == pytest.approx(300.0)
    # 5-minute slot grid is rejected under 1min, and 1-minute 09:31 is rejected under 5min (no silent drop)
    with pytest.raises(DataContractError, match="Off-grid"):
        _agg(rows, frequency="5min")


# --------------------------------------------------------------------------------------------- T10 math
def test_t10_zero_bursts_is_ok_with_zero_count_and_nan_direction():
    r = _agg(burst_rows("A.SH", D, {})).iloc[0]
    assert r["feature_status"] == "OK"
    assert r["burst_count"] == 0 and r["burst_share"] == 0.0
    assert np.isnan(r["burst_dominance"]) and np.isnan(r["burst_concentration"])
    assert not r["single_burst_flag"] and r["burst_regime"] == "NO_BURST"
    assert r["peak_ratio"] == pytest.approx(1.0)


@pytest.mark.parametrize("sign, regime_dom", [(1.0, 1.0), (-1.0, -1.0)])
def test_t10_single_burst_concentration_one_and_flag(sign, regime_dom):
    r = _agg(burst_rows("A.SH", D, {7: {"volume": 500.0, "body_efficiency": 0.4 * sign, "is_burst": True}})).iloc[0]
    assert r["burst_count"] == 1
    assert r["single_burst_flag"]
    assert r["burst_concentration"] == 1.0
    assert r["burst_dominance"] == pytest.approx(regime_dom)
    assert r["burst_share"] == pytest.approx(500.0 / (47 * 100.0 + 500.0))
    assert r["burst_regime"] == "ISOLATED_SINGLE_BURST"
    assert r["peak_ratio"] == pytest.approx(5.0)


def test_t10_two_way_offsetting_bursts_cancel():
    spec = {3: {"volume": 800.0, "body_efficiency": 0.5, "is_burst": True},
            30: {"volume": 800.0, "body_efficiency": -0.5, "is_burst": True}}
    r = _agg(burst_rows("A.SH", D, spec)).iloc[0]
    assert r["burst_count"] == 2
    assert r["burst_dominance"] == pytest.approx(0.0, abs=1e-15)
    assert r["burst_concentration"] == pytest.approx(0.0, abs=1e-15)  # equal weights -> HHI = 1/n
    assert r["burst_signed_Bull_weight_share"] == pytest.approx(0.5)
    assert r["burst_share"] == pytest.approx(1600.0 / (46 * 100.0 + 1600.0))
    assert r["burst_regime"] == "TWO_WAY_OFFSETTING"


def test_t10_hand_computed_weights_hhi_and_direction_agreement():
    spec = {
        5: {"volume": 300.0, "rel_vol": 3.0, "baseline": 100.0, "body_efficiency": 0.5, "is_burst": True},
        20: {"volume": 500.0, "rel_vol": 5.0, "baseline": 100.0, "body_efficiency": 0.2, "is_burst": True},
        40: {"volume": 10000.0, "rel_vol": 100.0, "baseline": 100.0, "body_efficiency": -0.8, "is_burst": True},
    }
    rows = burst_rows("A.SH", D, spec)
    V = 45 * 100.0 + 300.0 + 500.0 + 10000.0
    # hand formula: w = V_k/V * min(R/2.5, 10) * |E|   (third burst capped at 10x)
    w1 = 300.0 / V * (3.0 / 2.5) * 0.5
    w2 = 500.0 / V * (5.0 / 2.5) * 0.2
    w3 = 10000.0 / V * 10.0 * 0.8
    W = w1 + w2 + w3
    dom = (w1 + w2 - w3) / W
    hhi = (w1 / W) ** 2 + (w2 / W) ** 2 + (w3 / W) ** 2
    conc = (hhi - 1 / 3) / (1 - 1 / 3)

    for dir_val, agree in ((+0.7, (w1 + w2) / W), (-0.7, w3 / W), (0.0, np.nan)):
        daily = pd.DataFrame({"symbol": ["A.SH"], "trade_date": [D], "volume": [V], "B0_DIR": [dir_val]})
        r = _agg(rows, daily_ref=daily).iloc[0]
        assert r["burst_count"] == 3
        assert r["burst_share"] == pytest.approx(10800.0 / V)
        assert r["burst_dominance"] == pytest.approx(dom, rel=1e-12)
        assert r["burst_concentration"] == pytest.approx(conc, rel=1e-12)
        assert r["peak_ratio"] == pytest.approx(100.0)
        assert r["burst_regime"] == "BEAR_DOMINATED_BURSTS"
        if np.isnan(agree):
            assert np.isnan(r["burst_direction_agreement"])
        else:
            assert r["burst_direction_agreement"] == pytest.approx(agree, rel=1e-12)
        assert r["vol_recon_status"] == "RECONCILED_OK"


def test_t10_directionless_bursts_keep_ok_counts_not_nan():
    spec = {9: {"volume": 400.0, "body_efficiency": 0.0, "is_burst": True}}  # only possible if eff threshold = 0
    r = _agg(burst_rows("A.SH", D, spec)).iloc[0]
    assert r["feature_status"] == "OK"
    assert r["burst_count"] == 1 and r["burst_share"] > 0
    assert np.isnan(r["burst_dominance"])
    assert r["burst_regime"] == "DIRECTIONLESS_BURSTS"


# --------------------------------------------------------------------------------------------- daily_ref
def test_daily_ref_reconciliation_statuses_and_duplicate_keys():
    rows = burst_rows("A.SH", D, {})
    tot = rows["volume"].sum()

    def ref(v):
        return pd.DataFrame({"symbol": ["A.SH"], "trade_date": [D], "volume": [v]})

    assert _agg(rows).loc[0, "vol_recon_status"] == "RECONCILIATION_UNKNOWN"
    assert np.isnan(_agg(rows).loc[0, "vol_recon_error"])
    assert _agg(rows, daily_ref=ref(tot * 1.01)).loc[0, "vol_recon_status"] == "RECONCILED_OK"
    div = _agg(rows, daily_ref=ref(tot * 1.10)).iloc[0]
    assert div["vol_recon_status"] == "RECONCILIATION_DIVERGENCE"
    assert div["vol_recon_error"] == pytest.approx(abs(tot - tot * 1.10) / (tot * 1.10))
    mm = _agg(rows, daily_ref=ref(0.0)).iloc[0]
    assert mm["vol_recon_status"] == "RECONCILIATION_MISMATCH" and np.isnan(mm["vol_recon_error"])  # never inf
    other = pd.DataFrame({"symbol": ["B.SH"], "trade_date": [D], "volume": [tot]})
    assert _agg(rows, daily_ref=other).loc[0, "vol_recon_status"] == "RECONCILIATION_UNKNOWN"
    with pytest.raises(DataContractError, match="Duplicate"):
        _agg(rows, daily_ref=pd.concat([ref(tot), ref(tot)]))
    with pytest.raises(DataContractError, match="volume"):
        _agg(rows, daily_ref=ref(tot).drop(columns=["volume"]))


def test_csv_round_trip_string_time_slots_give_identical_features(tmp_path):
    dates = bdays(20)
    panel = make_panel(["600000.SH"], dates, lambda s, d, k: 4000.0 if (d == 19 and k == 3) else 1000.0)
    det = detect_bursts(panel)
    direct = aggregate_daily_features(det)
    p = tmp_path / "bars.csv"
    det.to_csv(p, index=False)
    reread = aggregate_daily_features(pd.read_csv(p))
    pd.testing.assert_frame_equal(direct, reread)
    assert direct.set_index("trade_date").loc[dates[19], "burst_count"] == 1


# --------------------------------------------------------------------------------------------- T11
def test_t11_concentrated_microbursts_vs_uniform_volume_expansion_are_distinguished():
    dates = bdays(21)
    total_day = 48 * 2000.0  # both test days carry exactly 2x normal daily volume

    def uniform(s, d, k):
        return 2000.0 if d == 20 else 1000.0

    def concentrated(s, d, k):
        if d != 20:
            return 1000.0
        return (total_day - 45 * 1000.0) / 3 if k in (4, 17, 33) else 1000.0

    u = compute_mbv_daily_pipeline(make_panel(["A.SH"], dates, uniform)).set_index("trade_date").loc[dates[20]]
    c = compute_mbv_daily_pipeline(make_panel(["A.SH"], dates, concentrated)).set_index("trade_date").loc[dates[20]]
    assert u["minute_total_volume"] == pytest.approx(c["minute_total_volume"]) == pytest.approx(total_day)
    assert u["feature_status"] == c["feature_status"] == "OK"
    assert u["burst_count"] == 0 and u["burst_share"] == 0.0 and u["burst_regime"] == "NO_BURST"
    assert c["burst_count"] == 3
    assert c["burst_share"] == pytest.approx((total_day - 45_000.0) / total_day)
    assert c["peak_ratio"] == pytest.approx(17_000.0 / 1000.0)
    assert c["burst_regime"] == "BULL_DOMINATED_BURSTS"
