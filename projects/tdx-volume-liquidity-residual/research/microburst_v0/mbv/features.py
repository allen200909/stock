"""Intraday relative volume, body efficiency proxy, and microburst event detection."""
from __future__ import annotations

from typing import Union

import numpy as np
import pandas as pd

from mbv.baselines import build_tod_baseline
from mbv.schema import DataContractError, ensure_finite_numeric, ensure_nonmissing_symbol, ensure_valid_ohlc


def _align_baseline(
    work: pd.DataFrame,
    baseline: Union[pd.DataFrame, pd.Series, None],
    *,
    lookback_days: int = 20,
    min_history_days: int = 15,
) -> pd.DataFrame:
    """Align baseline strictly on `(symbol, trade_date, time_slot)` and guard zero/invalid baselines."""
    key_cols = ["symbol", "trade_date", "time_slot"]

    if baseline is None:
        base_df = build_tod_baseline(
            work, lookback_days=lookback_days, min_history_days=min_history_days
        )
    elif isinstance(baseline, pd.DataFrame):
        required = {"symbol", "trade_date", "time_slot", "baseline"}
        missing = required.difference(baseline.columns)
        if missing:
            raise DataContractError(
                f"Baseline DataFrame must carry full key {sorted(required)}; missing {sorted(missing)}"
            )
        base_df = baseline.copy()
        base_df["symbol"] = ensure_nonmissing_symbol(base_df["symbol"])
        base_df["trade_date"] = pd.to_datetime(base_df["trade_date"], errors="raise").dt.strftime("%Y-%m-%d")
        if base_df.duplicated(subset=key_cols).any():
            raise DataContractError("Duplicate (symbol, trade_date, time_slot) keys in baseline DataFrame")
        if "baseline_status" not in base_df.columns:
            base_df["baseline_status"] = np.where(
                base_df["baseline"].isna(),
                "INSUFFICIENT_HISTORY",
                np.where(base_df["baseline"] <= 0.0, "BASELINE_INVALID", "OK"),
            )
        if "history_positive_days" not in base_df.columns:
            base_df["history_positive_days"] = np.where(base_df["baseline"].notna() & (base_df["baseline"] > 0), min_history_days, 0)
    elif isinstance(baseline, pd.Series):
        # Accept MultiIndex Series keyed by (symbol, trade_date, time_slot);
        # allow clock-time Series ONLY for a single-symbol, single-session isolated slice (unit test helper).
        if isinstance(baseline.index, pd.MultiIndex) and baseline.index.nlevels == 3:
            base_df = baseline.rename("baseline").reset_index()
            base_df.columns = ["symbol", "trade_date", "time_slot", "baseline"]
            base_df["trade_date"] = pd.to_datetime(base_df["trade_date"], errors="raise").dt.strftime("%Y-%m-%d")
        else:
            if work["symbol"].nunique() > 1 or work["trade_date"].nunique() > 1:
                raise DataContractError(
                    "Clock-time-only baseline Series is forbidden across multiple symbols or dates; "
                    "pass a (symbol, trade_date, time_slot) baseline DataFrame from build_tod_baseline()."
                )
            sym_val = work["symbol"].iloc[0]
            date_val = work["trade_date"].iloc[0]
            base_df = pd.DataFrame({
                "symbol": sym_val,
                "trade_date": date_val,
                "time_slot": list(baseline.index),
                "baseline": baseline.to_numpy(dtype=float),
            })
        base_df["baseline_status"] = np.where(
            base_df["baseline"].isna(),
            "INSUFFICIENT_HISTORY",
            np.where(base_df["baseline"] <= 0.0, "BASELINE_INVALID", "OK"),
        )
        base_df["history_positive_days"] = np.where(
            base_df["baseline"].notna() & (base_df["baseline"] > 0.0), min_history_days, 0
        )
    else:
        raise DataContractError(f"Unsupported baseline object type: {type(baseline).__name__}")

    merged = work.merge(
        base_df[key_cols + ["baseline", "history_positive_days", "baseline_status"]],
        on=key_cols,
        how="left",
    )
    merged["baseline_status"] = merged["baseline_status"].fillna("INSUFFICIENT_HISTORY")
    merged["history_positive_days"] = merged["history_positive_days"].fillna(0).astype(int)
    return merged


def detect_bursts(
    df: pd.DataFrame,
    baseline: Union[pd.DataFrame, pd.Series, None] = None,
    rel_vol_threshold: float = 2.5,
    body_eff_threshold: float = 0.10,
    *,
    tick_size: float = 0.01,
    lookback_days: int = 20,
    min_history_days: int = 15,
    threshold: float | None = None,
    rel_vol_th: float | None = None,
    eff_th: float | None = None,
) -> pd.DataFrame:
    """Detect intraday microburst events with full key alignment, body efficiency, and zero-baseline guard.

    Formula (RFC Section 4.1–4.2):
      R_{t,k} = V_{t,k} / B_{t,k}   for B_{t,k} > 0, else NaN (`BASELINE_INVALID` / `INSUFFICIENT_HISTORY`)
      E_{t,k} = (C_{t,k} - O_{t,k}) / max(H_{t,k} - L_{t,k}, tick_size)
      I_{t,k} = 1{ R_{t,k} >= rel_vol_threshold } * 1{ |E_{t,k}| >= body_eff_threshold }

    Note: `E_{t,k}` is a candle body-efficiency proxy from minute OHLC, NOT true order-flow imbalance.
    """
    if threshold is not None:
        rel_vol_threshold = float(threshold)
    if rel_vol_th is not None:
        rel_vol_threshold = float(rel_vol_th)
    if eff_th is not None:
        body_eff_threshold = float(eff_th)
    if rel_vol_threshold <= 0 or body_eff_threshold < 0 or tick_size <= 0:
        raise DataContractError("Burst thresholds and tick_size must be valid positive numbers")
    if df is None or df.empty:
        raise DataContractError("Input DataFrame to detect_bursts must not be empty")

    required = {"symbol", "ts", "open", "high", "low", "close", "volume"}
    missing = required.difference(df.columns)
    if missing:
        raise DataContractError(f"Missing required columns for burst detection: {sorted(missing)}")

    work = df.copy()
    work["symbol"] = ensure_nonmissing_symbol(work["symbol"])
    for col in ("open", "high", "low", "close"):
        work[col] = ensure_finite_numeric(work[col], col, strictly_positive=True)
    work["volume"] = ensure_finite_numeric(work["volume"], "volume", non_negative=True)
    ensure_valid_ohlc(work)

    if work["ts"].isna().any():
        raise DataContractError("ts contains null/NaN values")
    ts_parsed = pd.to_datetime(work["ts"], errors="raise")
    work["trade_date"] = ts_parsed.dt.strftime("%Y-%m-%d")
    work["time_slot"] = ts_parsed.dt.time

    if work.duplicated(subset=["symbol", "trade_date", "time_slot"]).any():
        raise DataContractError("Duplicate (symbol, trade_date, time_slot) records in detect_bursts")

    aligned = _align_baseline(
        work, baseline, lookback_days=lookback_days, min_history_days=min_history_days
    )

    # Zero or non-positive baseline NEVER produces inf; force baseline_valid = False and ratio = NaN
    b_vals = pd.to_numeric(aligned["baseline"], errors="coerce").astype(float)
    zero_or_neg = b_vals.notna() & (b_vals <= 0.0)
    if zero_or_neg.any():
        aligned.loc[zero_or_neg, "baseline_status"] = "BASELINE_INVALID"
    valid_base = np.isfinite(b_vals.to_numpy(dtype=float)) & (b_vals.to_numpy(dtype=float) > 0.0)
    safe_base = b_vals.where(valid_base, np.nan)
    aligned["baseline"] = safe_base

    rel_vol = aligned["volume"] / safe_base
    # Guarantee no inf/-inf ever escapes
    rel_vol = rel_vol.where(np.isfinite(rel_vol.to_numpy(dtype=float)), np.nan)
    aligned["rel_vol"] = rel_vol
    aligned["relative_volume"] = rel_vol

    denom = (aligned["high"] - aligned["low"]).clip(lower=tick_size)
    eff = (aligned["close"] - aligned["open"]) / denom
    aligned["body_efficiency"] = eff
    aligned["eff"] = eff

    is_burst = (
        valid_base
        & aligned["rel_vol"].ge(rel_vol_threshold)
        & aligned["body_efficiency"].abs().ge(body_eff_threshold)
    )
    aligned["is_burst"] = is_burst.fillna(False).astype(bool)
    aligned["burst_direction"] = np.where(
        ~aligned["is_burst"],
        0,
        np.where(aligned["body_efficiency"] > 0.0, 1, -1),
    )
    return aligned


# Backwards-compatible alias
detect_bursts_v2 = detect_bursts
