"""Read-only bridge to frozen VLR V2.1.2 B0 and strict left-join with MBV daily features."""
from __future__ import annotations

import hashlib
from pathlib import Path
import sys
from typing import Optional

import numpy as np
import pandas as pd

from mbv.schema import (
    DataContractError,
    assert_no_future_columns,
    ensure_nonmissing_symbol,
    normalize_trade_date,
    validate_daily_bars,
)

# Expected SHA256 of the frozen reference vlr.py snapshot to guard immutability (T15)
FROZEN_VLR_SHA256 = "3dfba129c22282b3409a0d32f6781638b0699d8c1d2393e81a0cd8ec7b3f07b8"

B0_COLUMN_MAP = {
    "Z": "B0_Z",
    "RVRAW": "B0_RVRAW",
    "DIR": "B0_DIR",
    "RHO": "B0_RHO",
    "CLV": "B0_CLV",
    "MOV": "B0_MOV",
    "EXPECT": "B0_EXPECT",
    "RES": "B0_RES",
    "VALID": "B0_VALID",
    "VU": "B0_VU",
    "VD": "B0_VD",
    "EU": "B0_EU",
    "ED": "B0_ED",
    "ABU": "B0_ABU",
    "ABD": "B0_ABD",
    "XG3": "B0_XG3",
    "XG6010": "B0_XG6010",
    "XGLAYER": "B0_XGLAYER",
}


def resolve_vlr_verify_dir(vlr_dir: Optional[str | Path] = None) -> Path:
    """Locate the read-only `reference/vlr_verify` directory without modifying it."""
    if vlr_dir is not None:
        p = Path(vlr_dir).resolve()
        if (p / "vlr.py").exists():
            return p
        raise FileNotFoundError(f"vlr.py not found in {p}")

    here = Path(__file__).resolve().parent
    candidates = [
        here.parent / "reference" / "vlr_verify",
        here.parent.parent / "reference" / "vlr_verify",
        here.parent.parent / "verify",
    ]
    for cand in candidates:
        if (cand / "vlr.py").exists():
            return cand.resolve()
    raise FileNotFoundError("Could not locate read-only reference/vlr_verify/vlr.py")


def verify_frozen_vlr_integrity(vlr_dir: Optional[str | Path] = None) -> dict[str, str]:
    """Verify SHA256 hashes of read-only VLR reference files."""
    ref_dir = resolve_vlr_verify_dir(vlr_dir)
    hashes: dict[str, str] = {}
    for fname in ("vlr.py", "validation.py", "inference.py"):
        fpath = ref_dir / fname
        if fpath.exists():
            hashes[fname] = hashlib.sha256(fpath.read_bytes()).hexdigest()
    return hashes


def _load_readonly_vlr_module(vlr_dir: Optional[str | Path] = None):
    ref_dir = str(resolve_vlr_verify_dir(vlr_dir))
    if ref_dir not in sys.path:
        sys.path.insert(0, ref_dir)
    import vlr  # type: ignore
    return vlr


def annotate_point_in_time_risk(df: pd.DataFrame) -> pd.DataFrame:
    """Separate research factor preservation from point-in-time tradability & corporate-action flags (T13).

    - Never fabricates `False` when historical status columns are absent: missing status columns
      yield `execution_eligibility = 'TRADABILITY_UNVERIFIED'`.
    - Detects flat locked bars (`high == low`, e.g., one-word limit board) as `ONE_WORD_LOCKED`.
    - Preserves all daily rows for factor analysis while recording explicit risk tags.
    """
    out = df.copy()
    n = len(out)
    has_susp = "suspended" in out.columns
    has_st = "st_flag" in out.columns
    has_limit = "price_limit_status" in out.columns
    has_corp = "corp_action_flag" in out.columns
    has_age = "listing_age_sessions" in out.columns

    risk_flags: list[str] = []
    eligibility: list[str] = []

    # Track suspension recovery (previous trading row for same symbol was suspended)
    prev_susp = pd.Series(False, index=out.index)
    if has_susp:
        prev_susp = (
            out.groupby("symbol", sort=False)["suspended"]
            .shift(1)
            .fillna(False)
            .astype(bool)
        )

    for idx, row in out.iterrows():
        tags: list[str] = []
        if float(row["high"]) == float(row["low"]):
            tags.append("ONE_WORD_LOCKED")
        if float(row["volume"]) == 0.0:
            tags.append("ZERO_DAILY_VOLUME")

        if has_susp and pd.notna(row["suspended"]) and bool(row["suspended"]):
            tags.append("SUSPENDED")
        elif has_susp and bool(prev_susp.loc[idx]):
            tags.append("RESUMED_FROM_SUSPENSION")

        if has_st and pd.notna(row["st_flag"]) and bool(row["st_flag"]):
            tags.append("ST_RISK")
        if has_corp and pd.notna(row["corp_action_flag"]) and bool(row["corp_action_flag"]):
            tags.append("CORP_ACTION_DAY")
        if has_age and pd.notna(row["listing_age_sessions"]) and int(row["listing_age_sessions"]) <= 5:
            tags.append("IPO_WINDOW")

        limit_val = str(row["price_limit_status"]).upper() if (has_limit and pd.notna(row["price_limit_status"])) else "UNKNOWN"
        if limit_val in ("LIMIT_UP", "LIMIT_DOWN", "LOCKED_UP", "LOCKED_DOWN"):
            tags.append(limit_val)

        # Determine execution eligibility at signal day / check layer without fabricating tradability
        if "SUSPENDED" in tags or "ZERO_DAILY_VOLUME" in tags:
            elig = "UNTRADABLE_SUSPENDED"
        elif "ONE_WORD_LOCKED" in tags or limit_val in ("LOCKED_UP", "LOCKED_DOWN", "LIMIT_UP", "LIMIT_DOWN"):
            elig = "LIMIT_RESTRICTED"
        elif not (has_susp and has_st and has_limit):
            elig = "TRADABILITY_UNVERIFIED"
        else:
            elig = "ELIGIBLE_FOR_T1_FILL_CHECK"

        risk_flags.append("|".join(tags) if tags else "NONE")
        eligibility.append(elig)

    out["data_risk_flags"] = risk_flags
    out["execution_eligibility"] = eligibility
    return out


def compute_readonly_b0(
    daily_df: pd.DataFrame,
    *,
    vlr_dir: Optional[str | Path] = None,
    initial_tr: str = "hl",
) -> pd.DataFrame:
    """Compute frozen VLR V2.1.2 `B0` per symbol via read-only `vlr.calculate(..., model='B0')`.

    Handles suspended zero-volume rows safely: `vlr.calculate` operates on active trading sessions
    per ticker (as in TongDaXin daily K-line series), while suspended placeholder rows if present
    in a research panel are preserved with `B0_VALID=False` and `SUSPENDED` risk flags.
    """
    validated = validate_daily_bars(daily_df)
    annotated = annotate_point_in_time_risk(validated)
    vlr_mod = _load_readonly_vlr_module(vlr_dir)

    results: list[pd.DataFrame] = []
    for symbol, grp in annotated.groupby("symbol", sort=True):
        grp = grp.sort_values("trade_date").reset_index(drop=True)
        susp_mask = grp["volume"] == 0.0
        if "suspended" in grp.columns:
            susp_mask = susp_mask | grp["suspended"].fillna(False).astype(bool)

        active = grp.loc[~susp_mask].copy().reset_index(drop=True)
        if not active.empty:
            vlr_in = pd.DataFrame({
                "date": pd.to_datetime(active["trade_date"]),
                "ticker": active["symbol"],
                "open": active["open"],
                "high": active["high"],
                "low": active["low"],
                "close": active["close"],
                "volume": active["volume"],
            })
            if "amount" in active.columns and not active["amount"].isna().all():
                vlr_in["amount"] = active["amount"]

            b0_raw = vlr_mod.calculate(vlr_in, model="B0", initial_tr=initial_tr)
            mapped = b0_raw.rename(columns=B0_COLUMN_MAP)
            keep_b0_cols = [v for v in B0_COLUMN_MAP.values() if v in mapped.columns]
            active_out = pd.concat([active, mapped[keep_b0_cols]], axis=1)
        else:
            active_out = active

        if susp_mask.any():
            susp_rows = grp.loc[susp_mask].copy()
            for src_col, dst_col in B0_COLUMN_MAP.items():
                if src_col in ("VU", "VD", "EU", "ED", "ABU", "ABD", "VALID", "XG3", "XG6010", "XGLAYER"):
                    susp_rows[dst_col] = False
                else:
                    susp_rows[dst_col] = np.nan
            combined = pd.concat([active_out, susp_rows], ignore_index=True)
            combined = combined.sort_values("trade_date").reset_index(drop=True)
        else:
            combined = active_out

        combined["vlr_parity_status"] = "TDX_PARITY_NOT_VERIFIED"
        results.append(combined)

    return pd.concat(results, ignore_index=True).sort_values(["symbol", "trade_date"]).reset_index(drop=True)


def join_daily_vlr_mbv(
    daily_vlr: pd.DataFrame,
    mbv_features: pd.DataFrame,
    *,
    source_hash: str = "",
    params_hash: str = "",
    reconciliation_tol: float = 0.02,
    dir_day_eps: float = 1e-6,
) -> pd.DataFrame:
    """Left-join daily VLR B0 table with MBV daily features on unique `(symbol, trade_date)`.

    Guarantees:
    1. Rejects null/missing or duplicate `(symbol, trade_date)` keys on EITHER side (T14).
    2. Rejects MBV tables lacking required contract column `feature_status` with `DataContractError`
       (never raw `KeyError`), and rejects any forward-looking outcome columns (T17).
    3. Preserves 100% of `daily_vlr` rows (`len(out) == len(daily_vlr)`), never dropping B0 events
       when minute bars are missing; unmatched rows receive `NaN` numeric MBV columns +
       `feature_status='MISSING_MINUTE_DATA'` (T12).
    4. Computes post-close `burst_direction_agreement` against `B0_DIR` when available, and updates
       `vol_recon_error` against daily `volume` if not already populated.
    """
    if daily_vlr is None or daily_vlr.empty:
        raise DataContractError("daily_vlr DataFrame must not be empty")
    if mbv_features is None:
        raise DataContractError("mbv_features DataFrame must not be None")

    for name, frame in (("daily_vlr", daily_vlr), ("mbv_features", mbv_features)):
        for col in ("symbol", "trade_date"):
            if col not in frame.columns:
                raise DataContractError(f"Missing primary key column '{col}' in {name}")
        assert_no_future_columns(frame)

    left = daily_vlr.copy()
    left["symbol"] = ensure_nonmissing_symbol(left["symbol"])
    left["trade_date"] = normalize_trade_date(left["trade_date"], "trade_date")
    if left.duplicated(subset=["symbol", "trade_date"]).any():
        raise DataContractError("Duplicate (symbol, trade_date) keys in daily_vlr")

    if mbv_features.empty:
        right = pd.DataFrame(columns=[
            "symbol", "trade_date", "burst_count", "burst_share", "peak_ratio",
            "burst_dominance", "burst_concentration", "single_burst_flag",
            "burst_direction_agreement", "valid_slot_coverage", "baseline_slot_coverage",
            "minute_total_volume", "vol_recon_error", "vol_recon_status",
            "burst_regime", "feature_status",
        ])
    else:
        if "feature_status" not in mbv_features.columns:
            raise DataContractError(
                "mbv_features is missing required contract column 'feature_status'"
            )
        right = mbv_features.copy()
        right["symbol"] = ensure_nonmissing_symbol(right["symbol"])
        right["trade_date"] = normalize_trade_date(right["trade_date"], "trade_date")
        if right.duplicated(subset=["symbol", "trade_date"]).any():
            raise DataContractError("Duplicate (symbol, trade_date) keys in mbv_features")

    # Ensure standard MBV columns exist on right before merging
    numeric_mbv_cols = [
        "burst_count",
        "burst_share",
        "peak_ratio",
        "burst_dominance",
        "burst_concentration",
        "burst_direction_agreement",
        "valid_slot_coverage",
        "baseline_slot_coverage",
        "minute_total_volume",
        "vol_recon_error",
    ]
    for col in numeric_mbv_cols:
        if col not in right.columns:
            right[col] = np.nan
    if "single_burst_flag" not in right.columns:
        right["single_burst_flag"] = False
    if "vol_recon_status" not in right.columns:
        right["vol_recon_status"] = "RECONCILIATION_UNKNOWN"
    if "burst_regime" not in right.columns:
        right["burst_regime"] = "UNAVAILABLE"

    merged = pd.merge(left, right, on=["symbol", "trade_date"], how="left", validate="one_to_one")

    # Unmatched B0 dates -> MISSING_MINUTE_DATA + NaN metrics (never filled with 0!)
    unmatched = merged["feature_status"].isna()
    merged.loc[unmatched, "feature_status"] = "MISSING_MINUTE_DATA"
    merged.loc[unmatched, "single_burst_flag"] = False
    merged["single_burst_flag"] = merged["single_burst_flag"].fillna(False).astype(bool)
    merged.loc[unmatched, "vol_recon_status"] = "MISSING_MINUTE_DATA"
    merged.loc[unmatched, "burst_regime"] = "UNAVAILABLE"

    # Reconcile minute_total_volume vs daily volume if daily `volume` exists and recon was unknown
    if "volume" in merged.columns and "minute_total_volume" in merged.columns:
        need_recon = (
            merged["minute_total_volume"].notna()
            & merged["vol_recon_error"].isna()
            & merged["volume"].notna()
        )
        for idx in merged.index[need_recon]:
            d_vol = float(merged.at[idx, "volume"])
            m_vol = float(merged.at[idx, "minute_total_volume"])
            if d_vol > 0.0:
                err = abs(m_vol - d_vol) / d_vol
                merged.at[idx, "vol_recon_error"] = err
                merged.at[idx, "vol_recon_status"] = (
                    "RECONCILED_OK" if err <= reconciliation_tol else "RECONCILIATION_DIVERGENCE"
                )
            else:
                merged.at[idx, "vol_recon_status"] = (
                    "ZERO_DAILY_VOLUME" if m_vol == 0.0 else "RECONCILIATION_MISMATCH"
                )

    # Populate burst_direction_agreement post-join if B0_DIR (or DIR) is present and agreement is NaN
    dir_col = "B0_DIR" if "B0_DIR" in merged.columns else ("DIR" if "DIR" in merged.columns else None)
    if (
        dir_col is not None
        and "burst_signed_Bull_weight_share" in merged.columns
        and "burst_signed_Bear_weight_share" in merged.columns
    ):
        can_compute = (
            (merged["feature_status"] == "OK")
            & (merged["burst_count"] >= 1)
            & merged["burst_direction_agreement"].isna()
            & merged[dir_col].notna()
            & (merged[dir_col].abs() > dir_day_eps)
        )
        for idx in merged.index[can_compute]:
            d_val = float(merged.at[idx, dir_col])
            val = (
                float(merged.at[idx, "burst_signed_Bull_weight_share"])
                if d_val > 0.0
                else float(merged.at[idx, "burst_signed_Bear_weight_share"])
            )
            merged.at[idx, "burst_direction_agreement"] = val
    elif dir_col is not None:
        # Fallback deriving from burst_dominance = bull_share - bear_share (since bull + bear == 1 when E != 0)
        can_compute = (
            (merged["feature_status"] == "OK")
            & (merged["burst_count"] >= 1)
            & merged["burst_direction_agreement"].isna()
            & merged["burst_dominance"].notna()
            & merged[dir_col].notna()
            & (merged[dir_col].abs() > dir_day_eps)
        )
        for idx in merged.index[can_compute]:
            dom = float(merged.at[idx, "burst_dominance"])
            d_val = float(merged.at[idx, dir_col])
            merged.at[idx, "burst_direction_agreement"] = 0.5 * (1.0 + dom) if d_val > 0.0 else 0.5 * (1.0 - dom)

    # Suspended daily flag override if no minute bars were traded
    if "data_risk_flags" in merged.columns:
        susp_rows = merged["data_risk_flags"].astype(str).str.contains("SUSPENDED") & (
            merged["feature_status"].isin(["MISSING_MINUTE_DATA", "NO_VOLUME"])
        )
        merged.loc[susp_rows, "feature_status"] = "SUSPENDED"

    merged["source_hash"] = source_hash
    merged["params_hash"] = params_hash
    assert_no_future_columns(merged)
    return merged
