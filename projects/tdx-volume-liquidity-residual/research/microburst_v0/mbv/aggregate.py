"""Implementation of daily feature aggregation gates, HHI concentration, and reconciliation."""
from __future__ import annotations

from datetime import time
from typing import Optional

import numpy as np
import pandas as pd

from mbv.schema import (
    MBV_DAILY_FEATURE_COLS,
    DataContractError,
    ensure_finite_numeric,
    ensure_nonmissing_symbol,
    normalize_trade_date,
)
from mbv.sessions import Frequency, expected_session_slots, expected_slot_count, is_closing_auction_slot  # noqa: F401


def _classify_regime(burst_count: float, burst_share: float, burst_dominance: float, status: str) -> str:
    if status != "OK" or not np.isfinite(burst_count):
        return "UNAVAILABLE"
    if int(burst_count) == 0:
        return "NO_BURST"
    if np.isfinite(burst_dominance) and abs(burst_dominance) < 0.25 and burst_share >= 0.10:
        return "TWO_WAY_OFFSETTING"
    if int(burst_count) == 1:
        return "ISOLATED_SINGLE_BURST"
    if burst_dominance >= 0.25:
        return "BULL_DOMINATED_BURSTS"
    if burst_dominance <= -0.25:
        return "BEAR_DOMINATED_BURSTS"
    return "MIXED_BURSTS"


def _aggregate_one_session(
    grp: pd.DataFrame,
    *,
    expected_slots: int,
    min_slot_coverage: float = 0.95,
    rel_vol_threshold: float = 2.5,
    ratio_cap_multiple: float = 10.0,
    dir_day: float | None = None,
    dir_day_eps: float = 1e-6,
    daily_volume: float | None = None,
    reconciliation_tol: float = 0.02,
    recon_minute_volume: float | None = None,
    symbol: str | None = None,
    trade_date: str | None = None,
) -> dict:
    symbol = str(grp["symbol"].iloc[0]) if symbol is None else str(symbol)
    trade_date = str(grp["trade_date"].iloc[0]) if trade_date is None else str(trade_date)

    total_day_minute_vol = float(grp["volume"].sum())
    # Reconciliation always compares the FULL minute session volume (incl. any excluded auction slots)
    recon_vol = total_day_minute_vol if recon_minute_volume is None else float(recon_minute_volume)
    available_slots = len(grp)
    valid_slot_coverage = float(available_slots) / float(expected_slots)

    # Valid baseline slots
    b_series = pd.to_numeric(grp["baseline"], errors="coerce")
    base_ok_mask = b_series.notna() & np.isfinite(b_series.to_numpy(dtype=float)) & (b_series > 0.0)
    baseline_slot_coverage = float(base_ok_mask.sum()) / float(expected_slots)

    # Vol Reconciliation
    if daily_volume is None or not np.isfinite(daily_volume):
        vol_recon_error = np.nan
        vol_recon_status = "RECONCILIATION_UNKNOWN"
    elif daily_volume <= 0.0:
        vol_recon_error = np.nan if recon_vol == 0.0 else np.inf
        vol_recon_status = "ZERO_DAILY_VOLUME" if recon_vol == 0.0 else "RECONCILIATION_MISMATCH"
    else:
        vol_recon_error = abs(recon_vol - float(daily_volume)) / float(daily_volume)
        vol_recon_status = "RECONCILED_OK" if vol_recon_error <= reconciliation_tol else "RECONCILIATION_DIVERGENCE"
    if not np.isfinite(vol_recon_error):
        vol_recon_error = np.nan  # never emit inf; the status column carries the mismatch

    def _na_payload(status_code: str) -> dict:
        return {
            "symbol": symbol, "trade_date": trade_date, "burst_count": np.nan, "burst_share": np.nan,
            "peak_ratio": np.nan, "burst_dominance": np.nan, "burst_concentration": np.nan,
            "single_burst_flag": False, "burst_direction_agreement": np.nan,
            "burst_signed_Bull_weight_share": np.nan, "burst_signed_Bear_weight_share": np.nan,
            "valid_slot_coverage": valid_slot_coverage, "baseline_slot_coverage": baseline_slot_coverage,
            "minute_total_volume": recon_vol, "vol_recon_error": vol_recon_error,
            "vol_recon_status": vol_recon_status, "burst_regime": "UNAVAILABLE", "feature_status": status_code,
        }

    if total_day_minute_vol <= 0.0:
        return _na_payload("NO_VOLUME")
    if valid_slot_coverage + 1e-12 < min_slot_coverage:
        return _na_payload("LOW_COVERAGE")
    if baseline_slot_coverage + 1e-12 < min_slot_coverage:
        return _na_payload("INSUFFICIENT_HISTORY")

    eligible = grp.loc[base_ok_mask].copy()
    v_total_eligible = float(eligible["volume"].sum())
    if v_total_eligible <= 0.0:
        return _na_payload("NO_VOLUME")

    peak_ratio = float(eligible["rel_vol"].max())
    bursts = eligible.loc[eligible["is_burst"].astype(bool)].copy()
    n_bursts = int(len(bursts))

    if n_bursts == 0:
        return {
            "symbol": symbol, "trade_date": trade_date, "burst_count": 0, "burst_share": 0.0,
            "peak_ratio": peak_ratio, "burst_dominance": np.nan, "burst_concentration": np.nan,
            "single_burst_flag": False, "burst_direction_agreement": np.nan,
            "burst_signed_Bull_weight_share": np.nan, "burst_signed_Bear_weight_share": np.nan,
            "valid_slot_coverage": valid_slot_coverage, "baseline_slot_coverage": baseline_slot_coverage,
            "minute_total_volume": recon_vol, "vol_recon_error": vol_recon_error,
            "vol_recon_status": vol_recon_status, "burst_regime": "NO_BURST", "feature_status": "OK",
        }

    burst_share = float(bursts["volume"].sum()) / v_total_eligible
    eff_col = "body_efficiency"
    e_vals = bursts[eff_col].to_numpy(dtype=float)
    v_vals = bursts["volume"].to_numpy(dtype=float)
    r_vals = bursts["rel_vol"].to_numpy(dtype=float)

    capped_rel = np.minimum(r_vals / float(rel_vol_threshold), float(ratio_cap_multiple))
    weights = (v_vals / v_total_eligible) * capped_rel * np.abs(e_vals)
    w_sum = float(weights.sum())

    if not np.isfinite(w_sum) or w_sum <= 0.0:
        # Only reachable with body_eff_threshold == 0 and flat burst bodies: bursts exist (count/share are
        # defined) but carry no direction weight, so dominance/concentration/agreement are undefined (NaN).
        return {
            **_na_payload("OK"), "burst_count": n_bursts, "burst_share": burst_share, "peak_ratio": peak_ratio,
            "single_burst_flag": (n_bursts == 1), "burst_regime": "DIRECTIONLESS_BURSTS",
        }

    w_norm = weights / w_sum
    signs = np.sign(e_vals)
    dom = float(np.clip(np.sum(signs * w_norm), -1.0, 1.0))
    bull_w = float(np.sum(w_norm[signs > 0]))
    bear_w = float(np.sum(w_norm[signs < 0]))
    hhi = float(np.sum(w_norm ** 2))
    conc = 1.0 if n_bursts == 1 else float(np.clip((hhi - 1.0/n_bursts) / (1.0 - 1.0/n_bursts), 0.0, 1.0))
    
    agreement = np.nan
    if dir_day is not None and np.isfinite(dir_day) and abs(float(dir_day)) > dir_day_eps:
        agreement = bull_w if float(dir_day) > 0.0 else bear_w

    return {
        "symbol": symbol, "trade_date": trade_date, "burst_count": n_bursts, "burst_share": burst_share,
        "peak_ratio": peak_ratio, "burst_dominance": dom, "burst_concentration": conc,
        "single_burst_flag": (n_bursts == 1), "burst_direction_agreement": agreement,
        "burst_signed_Bull_weight_share": bull_w, "burst_signed_Bear_weight_share": bear_w,
        "valid_slot_coverage": valid_slot_coverage, "baseline_slot_coverage": baseline_slot_coverage,
        "minute_total_volume": total_day_minute_vol, "vol_recon_error": vol_recon_error,
        "vol_recon_status": vol_recon_status, "burst_regime": _classify_regime(n_bursts, burst_share, dom, "OK"),
        "feature_status": "OK",
    }


#: Stable output schema of :func:`aggregate_daily_features` (column order is part of the contract).
AGG_OUTPUT_COLS: tuple[str, ...] = MBV_DAILY_FEATURE_COLS + (
    "burst_signed_Bull_weight_share",
    "burst_signed_Bear_weight_share",
    "expected_slots",
    "observed_slots",
    "excluded_auction_volume",
    "frequency",
    "closing_auction_excluded",
)

_FLOAT_COLS = (
    "burst_count", "burst_share", "peak_ratio", "burst_dominance", "burst_concentration",
    "burst_direction_agreement", "valid_slot_coverage", "baseline_slot_coverage",
    "minute_total_volume", "vol_recon_error", "burst_signed_Bull_weight_share",
    "burst_signed_Bear_weight_share", "excluded_auction_volume",
)
_STR_COLS = ("symbol", "trade_date", "vol_recon_status", "burst_regime", "feature_status", "frequency")
_BOOL_COLS = ("single_burst_flag", "closing_auction_excluded")
_INT_COLS = ("expected_slots", "observed_slots")

AGG_REQUIRED_INPUT_COLS = (
    "symbol", "trade_date", "time_slot", "volume", "baseline", "rel_vol", "body_efficiency", "is_burst",
)


def empty_daily_feature_frame() -> pd.DataFrame:
    """Return a zero-row frame carrying the full, typed aggregation schema (never a column-less frame)."""
    return _coerce_output_types(pd.DataFrame({c: [] for c in AGG_OUTPUT_COLS}))


def _coerce_output_types(out: pd.DataFrame) -> pd.DataFrame:
    out = out.loc[:, list(AGG_OUTPUT_COLS)].copy()
    for c in _FLOAT_COLS:
        out[c] = pd.to_numeric(out[c], errors="raise").astype("float64")
    for c in _INT_COLS:
        out[c] = pd.to_numeric(out[c], errors="raise").astype("int64")
    for c in _BOOL_COLS:
        out[c] = out[c].astype(bool)
    for c in _STR_COLS:
        out[c] = out[c].astype(object)
    return out


def _parse_time_slots(series: pd.Series) -> pd.Series:
    """Accept `datetime.time` objects or 'HH:MM[:SS]' strings (CSV round-trip); reject anything else."""
    if series.isna().any():
        raise DataContractError("time_slot contains null values")

    def _one(v):
        if isinstance(v, time):
            return v
        if isinstance(v, str):
            try:
                return pd.Timestamp(f"2000-01-01 {v.strip()}").time()
            except (ValueError, TypeError) as exc:
                raise DataContractError(f"Unparseable time_slot value '{v}'") from exc
        raise DataContractError(f"time_slot must be datetime.time or 'HH:MM:SS' string, got {type(v).__name__}")

    return series.map(_one)


def _prepare_daily_ref(daily_ref: Optional[pd.DataFrame]) -> dict[tuple[str, str], tuple[float, float]]:
    """Validate daily reference and map `(symbol, trade_date) -> (daily_volume, dir_day)` one-to-one."""
    if daily_ref is None:
        return {}
    if not isinstance(daily_ref, pd.DataFrame):
        raise DataContractError("daily_ref must be a pandas DataFrame or None")
    for col in ("symbol", "trade_date", "volume"):
        if col not in daily_ref.columns:
            raise DataContractError(f"daily_ref missing required column '{col}'")
    ref = daily_ref.copy()
    ref["symbol"] = ensure_nonmissing_symbol(ref["symbol"])
    ref["trade_date"] = normalize_trade_date(ref["trade_date"], "daily_ref.trade_date")
    if ref.duplicated(subset=["symbol", "trade_date"]).any():
        raise DataContractError("Duplicate (symbol, trade_date) keys in daily_ref")
    ref["volume"] = ensure_finite_numeric(ref["volume"], "daily_ref.volume", non_negative=True)
    dir_col = "B0_DIR" if "B0_DIR" in ref.columns else ("DIR" if "DIR" in ref.columns else None)
    if dir_col is not None:
        dirs = pd.to_numeric(ref[dir_col], errors="coerce").astype(float)
        if np.isinf(dirs.to_numpy()).any():
            raise DataContractError(f"daily_ref.{dir_col} contains inf values")
    else:
        dirs = pd.Series(np.nan, index=ref.index)
    return {
        (s, d): (float(v), float(x))
        for s, d, v, x in zip(ref["symbol"], ref["trade_date"], ref["volume"], dirs)
    }


def aggregate_daily_features(
    df: pd.DataFrame,
    *,
    frequency: Frequency = "5min",
    exclude_closing_auction: bool = False,
    min_slot_coverage: float = 0.95,
    rel_vol_threshold: float = 2.5,
    ratio_cap_multiple: float = 10.0,
    daily_ref: Optional[pd.DataFrame] = None,
    reconciliation_tol: float = 0.02,
    dir_day_eps: float = 1e-6,
) -> pd.DataFrame:
    """Aggregate per-bar burst output of :func:`mbv.features.detect_bursts` into one row per `(symbol, trade_date)`.

    Contract:
    - Input must carry ``AGG_REQUIRED_INPUT_COLS``; `(symbol, trade_date, time_slot)` must be non-null and unique;
      `volume` finite >= 0; `rel_vol`/`baseline` finite or NaN (never inf); `body_efficiency` finite;
      `is_burst` only on bars with a valid positive baseline. Violations raise :class:`DataContractError`.
    - Every `time_slot` must be a canonical `frequency` session slot (240 for 1min / 48 for 5min). Off-grid
      slots are rejected, never silently dropped.
    - ``exclude_closing_auction=True`` removes the closing-auction slots (1min: 14:57-14:59, 5min: 14:55) from
      the feature universe and uses the reduced denominator (237 / 47). Their volume is reported in
      ``excluded_auction_volume`` and still counted in ``minute_total_volume`` for daily reconciliation.
    - ``daily_ref`` (optional) supplies daily ``volume`` and ``B0_DIR``/``DIR`` keyed one-to-one on
      `(symbol, trade_date)`; duplicate keys raise. Sessions absent from ``daily_ref`` get
      ``vol_recon_status='RECONCILIATION_UNKNOWN'`` (never a fabricated zero).
    - Status priority (fixed): ``NO_VOLUME`` > ``LOW_COVERAGE`` > ``INSUFFICIENT_HISTORY`` > ``OK``. Non-OK rows
      carry NaN count/share/direction/concentration. A valid no-burst day is ``OK`` with count 0 and share 0.
    - Empty input returns :func:`empty_daily_feature_frame` (full typed schema, zero rows).

    Burst direction is a minute-OHLC candle-body proxy, NOT true active buy/sell order flow.
    """
    if df is None:
        raise DataContractError("aggregate_daily_features input must not be None")
    if not 0.0 < float(min_slot_coverage) <= 1.0:
        raise DataContractError("min_slot_coverage must be in (0, 1]")
    if rel_vol_threshold <= 0 or ratio_cap_multiple <= 0 or reconciliation_tol < 0 or dir_day_eps < 0:
        raise DataContractError("Invalid aggregation thresholds")
    canonical_slots = expected_session_slots(frequency, exclude_closing_auction=False)  # validates frequency
    retained_slots = set(expected_session_slots(frequency, exclude_closing_auction=exclude_closing_auction))
    expected_slots = expected_slot_count(frequency, exclude_closing_auction=exclude_closing_auction)

    missing = [c for c in AGG_REQUIRED_INPUT_COLS if c not in df.columns]
    if missing:
        raise DataContractError(f"aggregate_daily_features input missing required columns: {missing}")
    if df.empty:
        return empty_daily_feature_frame()

    work = df.loc[:, list(AGG_REQUIRED_INPUT_COLS)].copy()
    work["symbol"] = ensure_nonmissing_symbol(work["symbol"])
    work["trade_date"] = normalize_trade_date(work["trade_date"], "trade_date")
    work["time_slot"] = _parse_time_slots(work["time_slot"])
    if work.duplicated(subset=["symbol", "trade_date", "time_slot"]).any():
        raise DataContractError("Duplicate (symbol, trade_date, time_slot) in aggregation")

    bad_slot = ~work["time_slot"].isin(set(canonical_slots))
    if bad_slot.any():
        raise DataContractError(
            f"Off-grid time_slot {work.loc[bad_slot, 'time_slot'].iloc[0]} for frequency '{frequency}'"
        )

    work["volume"] = ensure_finite_numeric(work["volume"], "volume", non_negative=True)
    work["body_efficiency"] = ensure_finite_numeric(work["body_efficiency"], "body_efficiency")
    for col in ("baseline", "rel_vol"):
        vals = pd.to_numeric(work[col], errors="coerce").astype(float)
        if np.isinf(vals.to_numpy()).any():
            raise DataContractError(f"{col} contains inf values")
        work[col] = vals
    if work["is_burst"].isna().any():
        raise DataContractError("is_burst contains null values")
    work["is_burst"] = work["is_burst"].astype(bool)
    base_ok = work["baseline"].notna() & (work["baseline"] > 0.0)
    if (work["is_burst"] & ~base_ok).any():
        raise DataContractError("is_burst=True on a bar without a valid positive baseline")
    if (work["is_burst"] & work["rel_vol"].isna()).any():
        raise DataContractError("is_burst=True on a bar with NaN rel_vol")

    ref_map = _prepare_daily_ref(daily_ref)
    in_scope = work["time_slot"].isin(retained_slots)

    rows: list[dict] = []
    for (symbol, trade_date), grp in work.groupby(["symbol", "trade_date"], sort=True):
        full_minute_vol = float(grp["volume"].sum())
        scoped = grp.loc[in_scope.loc[grp.index]]
        excluded_vol = float(grp.loc[~in_scope.loc[grp.index], "volume"].sum())
        daily_volume, dir_day = ref_map.get((symbol, trade_date), (None, None))

        rec = _aggregate_one_session(
            scoped,
            expected_slots=expected_slots,
            min_slot_coverage=min_slot_coverage,
            rel_vol_threshold=rel_vol_threshold,
            ratio_cap_multiple=ratio_cap_multiple,
            dir_day=dir_day,
            dir_day_eps=dir_day_eps,
            daily_volume=daily_volume,
            reconciliation_tol=reconciliation_tol,
            recon_minute_volume=full_minute_vol,
            symbol=symbol,
            trade_date=trade_date,
        )
        rec["expected_slots"] = expected_slots
        rec["observed_slots"] = int(len(scoped))
        rec["excluded_auction_volume"] = excluded_vol
        rec["frequency"] = frequency
        rec["closing_auction_excluded"] = bool(exclude_closing_auction)
        rows.append(rec)

    out = _coerce_output_types(pd.DataFrame(rows))
    if out.duplicated(subset=["symbol", "trade_date"]).any():  # pragma: no cover - defensive invariant
        raise DataContractError("Aggregation produced duplicate (symbol, trade_date) rows")
    return out.sort_values(["symbol", "trade_date"]).reset_index(drop=True)
