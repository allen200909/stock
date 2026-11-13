"""R6 T12–T15: strict left join, point-in-time risk tagging, join key contract, frozen VLR V2.1.2 B0 parity."""
from __future__ import annotations

import hashlib
import shutil
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from mbv.adapters import generate_synthetic_market_bundle
from mbv.join import (
    B0_COLUMN_MAP,
    FROZEN_REFERENCE_SHA256,
    annotate_point_in_time_risk,
    assert_frozen_vlr_integrity,
    compute_readonly_b0,
    join_daily_vlr_mbv,
    resolve_vlr_verify_dir,
)
from mbv.schema import DataContractError

PROJECT_ROOT = Path(__file__).resolve().parents[3]  # projects/tdx-volume-liquidity-residual
REF_DIR = Path(__file__).resolve().parents[1] / "reference" / "vlr_verify"

# SHA-256 of the frozen VLR V2.1.2 artefacts on origin/master (must never change on this branch).
FROZEN_REPO_FILES = {
    "indicator/volume_liquidity_residual_v2.1.2.tdx": "9913cceddbb5e58450c0e8a883c5b8b82217d02d574765c80503b3715564fcad",
    "selectors/strong_expansion_3d.tdx": "31a00ebaaac95784672be21ad8a5a0a27accc57b5e7b0fddfbd227fd32173da4",
    "selectors/strong_expansion_60d3_recent10.tdx": "2cb07ba1825932d38eea88d7c6e911abf18c98739bcc13558948dc7e0245fd9b",
    "selectors/strong_expansion_activity_layered.tdx": "99c46e672f04741ed04165a626f2f85db8f375626636a50ba812ab2921365886",
    "verify/vlr.py": "3dfba129c22282b3409a0d32f6781638b0699d8c1d2393e81a0cd8ec7b3f07b8",
    "verify/validation.py": "bc647ac1e64753a1bc2af15525a755b9162f646acd99e299a475ee96cc5a12d3",
    "verify/inference.py": "ed2243298785c93755f2a5cf20e5f9d930b544ce2e6523f9703508a07732bef1",
}


def _sha(p: Path) -> str:
    return hashlib.sha256(p.read_bytes()).hexdigest()


@pytest.fixture(scope="module")
def daily_panel() -> pd.DataFrame:
    return generate_synthetic_market_bundle(n_sessions=165, minute_tail_sessions=1)["daily"]


@pytest.fixture(scope="module")
def b0_table(daily_panel) -> pd.DataFrame:
    return compute_readonly_b0(daily_panel)


def _mbv_rows(b0: pd.DataFrame, n_dates: int = 5) -> pd.DataFrame:
    """Fixed-schema MBV rows for the last ``n_dates`` sessions of each symbol (others -> missing minute data)."""
    last = b0.groupby("symbol")["trade_date"].apply(lambda s: sorted(s)[-n_dates:]).explode()
    rows = []
    for sym, d in last.items():
        rows.append({"symbol": sym, "trade_date": d, "burst_count": 1.0, "burst_share": 0.2, "peak_ratio": 3.0,
                     "burst_dominance": 0.5, "burst_concentration": 1.0, "single_burst_flag": True,
                     "burst_direction_agreement": np.nan, "valid_slot_coverage": 1.0,
                     "baseline_slot_coverage": 1.0, "minute_total_volume": np.nan, "vol_recon_error": np.nan,
                     "vol_recon_status": "RECONCILIATION_UNKNOWN", "burst_regime": "BULL_BURST",
                     "feature_status": "OK"})
    return pd.DataFrame(rows)


# --------------------------------------------------------------------------------------------- T12
def test_t12_left_join_preserves_every_b0_row_and_never_zero_fills(b0_table):
    mbv = _mbv_rows(b0_table)
    out = join_daily_vlr_mbv(b0_table, mbv)
    assert len(out) == len(b0_table)
    assert out[["symbol", "trade_date"]].equals(b0_table[["symbol", "trade_date"]])
    # B0 columns are passed through untouched
    b0_cols = [c for c in B0_COLUMN_MAP.values() if c in b0_table.columns]
    assert len(b0_cols) == len(B0_COLUMN_MAP)
    pd.testing.assert_frame_equal(out[b0_cols], b0_table[b0_cols])
    matched = out.merge(mbv[["symbol", "trade_date"]], on=["symbol", "trade_date"], how="left", indicator=True)
    is_matched = (matched["_merge"] == "both").to_numpy()
    assert is_matched.sum() == len(mbv) == 15
    miss = out.loc[~is_matched]
    assert (miss["feature_status"] == "MISSING_MINUTE_DATA").all()
    assert miss[["burst_count", "burst_share", "peak_ratio", "burst_dominance"]].isna().all().all()
    assert (miss["single_burst_flag"] == False).all()  # noqa: E712
    # B0 events living on missing-minute days are still present (not dropped)
    assert int(b0_table["B0_EU"].sum()) == int(out["B0_EU"].sum())
    assert (out.loc[is_matched, "feature_status"] == "OK").all()


def test_t12_empty_mbv_table_yields_all_missing_with_fixed_schema(b0_table):
    out = join_daily_vlr_mbv(b0_table, pd.DataFrame(columns=["symbol", "trade_date", "feature_status"]))
    assert len(out) == len(b0_table)
    assert (out["feature_status"] == "MISSING_MINUTE_DATA").all()
    for col in ("burst_count", "burst_share", "burst_regime", "vol_recon_status"):
        assert col in out.columns
    assert out["burst_count"].isna().all()


# --------------------------------------------------------------------------------------------- T13
def _daily(rows):
    base = {"symbol": "600000.SH", "open": 10.0, "high": 10.5, "low": 9.8, "close": 10.2, "volume": 1e6}
    return pd.DataFrame([{**base, **r} for r in rows])


def test_t13_point_in_time_risk_tags_and_eligibility():
    df = _daily([
        {"trade_date": "2026-01-05", "suspended": False, "st_flag": False, "price_limit_status": "NONE",
         "corp_action_flag": False, "listing_age_sessions": 3},
        {"trade_date": "2026-01-06", "suspended": True, "st_flag": False, "price_limit_status": "NONE",
         "corp_action_flag": False, "listing_age_sessions": 4, "volume": 0.0, "open": 10.2, "high": 10.2,
         "low": 10.2, "close": 10.2},
        {"trade_date": "2026-01-07", "suspended": False, "st_flag": True, "price_limit_status": "LIMIT_UP",
         "corp_action_flag": True, "listing_age_sessions": 5, "open": 11.22, "high": 11.22, "low": 11.22,
         "close": 11.22},
        {"trade_date": "2026-01-08", "suspended": False, "st_flag": False, "price_limit_status": "NONE",
         "corp_action_flag": False, "listing_age_sessions": 6},
    ])
    out = annotate_point_in_time_risk(df).set_index("trade_date")
    f = out["data_risk_flags"].str.split("|")
    assert set(f["2026-01-05"]) == {"IPO_WINDOW"}
    assert out.loc["2026-01-05", "execution_eligibility"] == "ELIGIBLE_FOR_T1_FILL_CHECK"
    assert {"SUSPENDED", "ZERO_DAILY_VOLUME", "ONE_WORD_LOCKED", "IPO_WINDOW"} <= set(f["2026-01-06"])
    assert out.loc["2026-01-06", "execution_eligibility"] == "UNTRADABLE_SUSPENDED"
    assert {"RESUMED_FROM_SUSPENSION", "ST_RISK", "CORP_ACTION_DAY", "IPO_WINDOW", "LIMIT_UP",
            "ONE_WORD_LOCKED"} <= set(f["2026-01-07"])
    assert out.loc["2026-01-07", "execution_eligibility"] == "LIMIT_RESTRICTED"
    assert out.loc["2026-01-08", "data_risk_flags"] == "NONE"


def test_t13_missing_status_columns_never_fabricate_tradability():
    out = annotate_point_in_time_risk(_daily([{"trade_date": "2026-01-05"}, {"trade_date": "2026-01-06"}]))
    assert (out["execution_eligibility"] == "TRADABILITY_UNVERIFIED").all()
    assert (out["data_risk_flags"] == "NONE").all()
    assert "suspended" not in out.columns  # no fabricated False column


def test_t13_suspended_row_through_b0_and_join_is_flagged(daily_panel):
    panel = daily_panel.copy()
    sym = "600000.SH"
    d = sorted(panel.loc[panel["symbol"] == sym, "trade_date"])[-3]
    m = (panel["symbol"] == sym) & (panel["trade_date"] == d)
    px = float(panel.loc[m, "close"].iloc[0])
    panel.loc[m, ["open", "high", "low", "close", "volume", "amount"]] = [px, px, px, px, 0.0, 0.0]
    panel.loc[m, "suspended"] = True
    b0 = compute_readonly_b0(panel)
    row = b0[(b0["symbol"] == sym) & (b0["trade_date"] == d)].iloc[0]
    assert bool(row["B0_VALID"]) is False and bool(row["B0_EU"]) is False
    assert np.isnan(row["B0_Z"])
    assert "SUSPENDED" in row["data_risk_flags"]
    assert len(b0) == len(panel)
    joined = join_daily_vlr_mbv(b0, _mbv_rows(b0, 1))
    jrow = joined[(joined["symbol"] == sym) & (joined["trade_date"] == d)].iloc[0]
    assert jrow["feature_status"] == "SUSPENDED"
    nxt = b0[(b0["symbol"] == sym) & (b0["trade_date"] > d)].iloc[0]
    assert "RESUMED_FROM_SUSPENSION" in nxt["data_risk_flags"]


# --------------------------------------------------------------------------------------------- T14
@pytest.mark.parametrize("side", ["left", "right"])
def test_t14_duplicate_and_null_keys_rejected(b0_table, side):
    mbv = _mbv_rows(b0_table)
    left, right = b0_table.copy(), mbv.copy()
    target = left if side == "left" else right
    dup = pd.concat([target, target.iloc[[0]]], ignore_index=True)
    with pytest.raises(DataContractError, match="Duplicate"):
        join_daily_vlr_mbv(dup, right) if side == "left" else join_daily_vlr_mbv(left, dup)
    nul = target.copy()
    nul.loc[nul.index[0], "symbol"] = None
    with pytest.raises(DataContractError):
        join_daily_vlr_mbv(nul, right) if side == "left" else join_daily_vlr_mbv(left, nul)
    nul_d = target.copy()
    nul_d["trade_date"] = nul_d["trade_date"].astype(object)
    nul_d.loc[nul_d.index[0], "trade_date"] = None
    with pytest.raises(DataContractError):
        join_daily_vlr_mbv(nul_d, right) if side == "left" else join_daily_vlr_mbv(left, nul_d)


def test_t14_missing_contract_columns_raise_contract_error_not_keyerror(b0_table):
    mbv = _mbv_rows(b0_table)
    with pytest.raises(DataContractError, match="feature_status"):
        join_daily_vlr_mbv(b0_table, mbv.drop(columns=["feature_status"]))
    with pytest.raises(DataContractError, match="symbol"):
        join_daily_vlr_mbv(b0_table, mbv.drop(columns=["symbol"]))
    with pytest.raises(DataContractError, match="trade_date"):
        join_daily_vlr_mbv(b0_table.drop(columns=["trade_date"]), mbv)
    with pytest.raises(DataContractError, match="Forward-looking"):
        join_daily_vlr_mbv(b0_table, mbv.assign(fwd_ret_5d=0.0))
    with pytest.raises(DataContractError):
        join_daily_vlr_mbv(b0_table.iloc[0:0], mbv)


# --------------------------------------------------------------------------------------------- T15
def test_t15_readonly_b0_equals_direct_frozen_reference_calculation(daily_panel, b0_table):
    sys.path.insert(0, str(REF_DIR))
    import vlr  # type: ignore  # frozen reference, loaded read-only

    for sym, grp in daily_panel.groupby("symbol"):
        grp = grp.sort_values("trade_date").reset_index(drop=True)
        direct = vlr.calculate(
            pd.DataFrame({"date": pd.to_datetime(grp["trade_date"]), "ticker": grp["symbol"], "open": grp["open"],
                          "high": grp["high"], "low": grp["low"], "close": grp["close"],
                          "volume": grp["volume"], "amount": grp["amount"]}),
            model="B0", initial_tr="hl",
        ).rename(columns=B0_COLUMN_MAP)
        mine = b0_table[b0_table["symbol"] == sym].reset_index(drop=True)
        cols = list(B0_COLUMN_MAP.values())
        pd.testing.assert_frame_equal(mine[cols], direct[cols], check_exact=True, check_dtype=False)
    assert b0_table["B0_VALID"].sum() > 0 and b0_table["B0_EU"].sum() > 0
    assert (b0_table["vlr_parity_status"] == "TDX_PARITY_NOT_VERIFIED").all()


def test_t15_reference_snapshot_hashes_match_frozen_constants_and_repo_verify():
    assert resolve_vlr_verify_dir() == REF_DIR.resolve()
    hashes = assert_frozen_vlr_integrity()
    assert hashes == FROZEN_REFERENCE_SHA256
    for fname, h in FROZEN_REFERENCE_SHA256.items():
        repo_file = PROJECT_ROOT / "verify" / fname
        assert _sha(repo_file) == h, f"{repo_file} differs from frozen reference"


def test_t15_frozen_vlr_v212_indicator_selectors_verify_files_unchanged():
    for rel, expected in FROZEN_REPO_FILES.items():
        assert _sha(PROJECT_ROOT / rel) == expected, rel


def test_t15_tampered_reference_copy_fails_closed(tmp_path, daily_panel):
    tampered = tmp_path / "vlr_verify"
    shutil.copytree(REF_DIR, tampered, ignore=shutil.ignore_patterns("__pycache__"))
    assert assert_frozen_vlr_integrity(tampered) == FROZEN_REFERENCE_SHA256  # pristine copy passes
    (tampered / "vlr.py").write_text((tampered / "vlr.py").read_text() + "\n# tampered\n")
    with pytest.raises(DataContractError, match="integrity failure for vlr.py"):
        assert_frozen_vlr_integrity(tampered)
    with pytest.raises(DataContractError, match="integrity failure"):
        compute_readonly_b0(daily_panel, vlr_dir=tampered)
    (tampered / "inference.py").unlink()
    shutil.copy(REF_DIR / "vlr.py", tampered / "vlr.py")
    with pytest.raises(DataContractError, match="inference.py"):
        assert_frozen_vlr_integrity(tampered)
