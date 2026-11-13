"""Past-only rolling time-of-day (TOD) volume baseline and optional session EMA benchmark."""
from __future__ import annotations

import numpy as np
import pandas as pd

from mbv.schema import DataContractError, ensure_finite_numeric, ensure_nonmissing_symbol


def build_tod_baseline(
    df: pd.DataFrame,
    lookback_days: int = 20,
    min_history_days: int = 15,
) -> pd.DataFrame:
    """Compute past-only rolling time-of-day median volume baseline per `(symbol, trade_date, time_slot)`.

    Specification (RFC Section 4.1 & R4/R5 Critical Path):
    - Strictly isolated by `(symbol, time_slot)`.
    - Uses ONLY completed prior trading dates `u < t` (no current-day or future-day leakage).
    - Window consists of the most recent `lookback_days` (default 20) prior trading sessions for
      that `(symbol, time_slot)` in the dataset.
    - Within that prior window, only strictly positive volumes (`V > 0`) are eligible observations
      (zero-volume / suspended slots are excluded from both count and median).
    - Requires `positive_history_days >= min_history_days` (default 15, including 15..19 when fewer
      than 20 total sessions exist). Otherwise `baseline = NaN` and `baseline_status = 'INSUFFICIENT_HISTORY'`.
    - Fails closed if duplicate `(symbol, trade_date, time_slot)` rows exist (never silently sums).
    """
    if lookback_days < 1 or min_history_days < 1 or min_history_days > lookback_days:
        raise DataContractError(
            f"Invalid window parameters: lookback_days={lookback_days}, min_history_days={min_history_days}"
        )
    if df is None or df.empty:
        raise DataContractError("Input DataFrame for baseline computation must not be empty")
    if "symbol" not in df.columns or "volume" not in df.columns:
        raise DataContractError("Baseline input requires 'symbol' and 'volume' columns")
    if "ts" not in df.columns and not ("trade_date" in df.columns and "time_slot" in df.columns):
        raise DataContractError("Baseline input requires 'ts' or ('trade_date', 'time_slot')")

    work = df.copy()
    work["symbol"] = ensure_nonmissing_symbol(work["symbol"])
    work["volume"] = ensure_finite_numeric(work["volume"], "volume", non_negative=True)

    if "ts" in work.columns:
        if work["ts"].isna().any():
            raise DataContractError("ts contains null/NaN values")
        ts_parsed = pd.to_datetime(work["ts"], errors="raise")
        if "trade_date" not in work.columns:
            work["trade_date"] = ts_parsed.dt.strftime("%Y-%m-%d")
        else:
            if work["trade_date"].isna().any():
                raise DataContractError("trade_date contains null/NaN values")
            work["trade_date"] = pd.to_datetime(work["trade_date"], errors="raise").dt.strftime("%Y-%m-%d")
        if "time_slot" not in work.columns:
            work["time_slot"] = ts_parsed.dt.time
    else:
        if work["trade_date"].isna().any() or work["time_slot"].isna().any():
            raise DataContractError("trade_date / time_slot contains null values")
        work["trade_date"] = pd.to_datetime(work["trade_date"], errors="raise").dt.strftime("%Y-%m-%d")

    key_cols = ["symbol", "trade_date", "time_slot"]
    if work.duplicated(subset=key_cols).any():
        raise DataContractError(
            "Duplicate (symbol, trade_date, time_slot) records rejected in baseline computation"
        )

    work = work.sort_values(["symbol", "time_slot", "trade_date"]).reset_index(drop=True)

    # Build symbol-level session calendar from present trading dates so missing/zero slots on a session
    # still occupy a session step in the 20-session lookback window rather than pulling stale dates >20 sessions old.
    out_parts: list[pd.DataFrame] = []
    for symbol, sym_df in work.groupby("symbol", sort=False):
        sym_dates = sorted(sym_df["trade_date"].unique())
        slots = sorted(sym_df["time_slot"].unique())

        piv = sym_df.pivot(index="trade_date", columns="time_slot", values="volume").reindex(
            index=sym_dates, columns=slots
        )
        # Mask non-positive volumes to NaN so zero-volume bars do NOT count as positive history
        # and do NOT pull the median down to 0.0.
        pos_piv = piv.where(piv > 0.0, np.nan)

        shifted = pos_piv.shift(1)
        pos_count = shifted.notna().rolling(window=lookback_days, min_periods=1).sum()
        raw_med = shifted.rolling(window=lookback_days, min_periods=min_history_days).median()

        eligible = (pos_count >= min_history_days) & raw_med.notna() & (raw_med > 0.0)
        baseline_mat = raw_med.where(eligible, np.nan)

        # Unstack back and merge onto actual observed rows for this symbol
        base_long = (
            baseline_mat.stack(future_stack=True)
            .rename("baseline")
            .reset_index()
        )
        cnt_long = (
            pos_count.fillna(0.0)
            .astype(int)
            .stack(future_stack=True)
            .rename("history_positive_days")
            .reset_index()
        )
        merged_sym = sym_df[key_cols + ["volume"]].merge(
            base_long, on=["trade_date", "time_slot"], how="left"
        ).merge(
            cnt_long, on=["trade_date", "time_slot"], how="left"
        )

        status = np.where(
            merged_sym["history_positive_days"] < min_history_days,
            "INSUFFICIENT_HISTORY",
            np.where(
                merged_sym["baseline"].isna() | (merged_sym["baseline"] <= 0.0),
                "BASELINE_INVALID",
                "OK",
            ),
        )
        merged_sym["baseline_status"] = status
        out_parts.append(merged_sym)

    result = pd.concat(out_parts, ignore_index=True)
    result = result.sort_values(["symbol", "trade_date", "time_slot"]).reset_index(drop=True)
    return result


def compute_session_ema_benchmark(
    df: pd.DataFrame,
    *,
    span: int = 20,
    min_periods: int = 10,
) -> pd.DataFrame:
    """Optional benchmark (`baseline_method='session_ema'`, NOT V0.1 primary method).

    Explicitly lagged by 1 intraday bar within each `(symbol, trade_date)` session so current bar
    volume does not divide by itself, and resets across sessions and symbols.
    """
    if span < 2 or min_periods < 1:
        raise DataContractError("Invalid session_ema parameters")
    work = df.copy()
    work["symbol"] = ensure_nonmissing_symbol(work["symbol"])
    work["volume"] = ensure_finite_numeric(work["volume"], "volume", non_negative=True)
    ts_parsed = pd.to_datetime(work["ts"], errors="raise")
    work["trade_date"] = ts_parsed.dt.strftime("%Y-%m-%d")
    work["time_slot"] = ts_parsed.dt.time

    key_cols = ["symbol", "trade_date", "time_slot"]
    if work.duplicated(subset=key_cols).any():
        raise DataContractError("Duplicate (symbol, trade_date, time_slot) records rejected")

    work = work.sort_values(["symbol", "trade_date", "time_slot"]).reset_index(drop=True)
    parts: list[pd.DataFrame] = []
    for (_, _), grp in work.groupby(["symbol", "trade_date"], sort=False):
        grp = grp.copy()
        pos_v = grp["volume"].where(grp["volume"] > 0.0, np.nan)
        lagged = pos_v.shift(1)
        ema = lagged.ewm(span=span, min_periods=min_periods, adjust=False).mean()
        cnt = lagged.notna().cumsum()
        valid = (cnt >= min_periods) & ema.notna() & (ema > 0.0)
        grp["baseline"] = ema.where(valid, np.nan)
        grp["history_positive_days"] = cnt.astype(int)
        grp["baseline_status"] = np.where(
            cnt < min_periods,
            "INSUFFICIENT_HISTORY",
            np.where(valid, "OK_SESSION_EMA_BENCHMARK", "BASELINE_INVALID"),
        )
        parts.append(grp[key_cols + ["volume", "baseline", "history_positive_days", "baseline_status"]])
    return pd.concat(parts, ignore_index=True)


# Canonical aliases so all caller/test names map to the single past-only implementation
compute_rolling_tod_baseline = build_tod_baseline
compute_rolling_tod_baseline_v2 = build_tod_baseline
compute_tod_baseline = build_tod_baseline
