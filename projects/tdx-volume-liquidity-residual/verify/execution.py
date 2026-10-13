"""Daily long-only candidate checks, requiring an explicit exchange calendar.

Calendar must cover input dates and the intended next session. A missing next
bar is DATA_MISSING; an unavailable next session is PENDING, never a fill.
"""
from __future__ import annotations
import numpy as np
import pandas as pd
from validation import daily_dates, finite_numeric, strict_boolean

REQUIRED = {
    "date", "ticker", "RAW_SIGNAL", "amount", "is_st", "listing_age_days",
    "suspended", "limit_up_locked", "limit_down_locked",
}


def build_execution_table(bars: pd.DataFrame, *, trading_calendar,
                          min_turnover=50_000_000, min_listing_days=250):
    missing = REQUIRED - set(bars.columns)
    if missing:
        raise ValueError(f"Missing point-in-time columns: {sorted(missing)}")
    if not np.isfinite([min_turnover, min_listing_days]).all() or min(min_turnover, min_listing_days) < 0:
        raise ValueError("Thresholds must be finite and nonnegative")
    calendar = daily_dates(trading_calendar, "trading_calendar")
    if calendar.empty or not calendar.is_unique or not calendar.is_monotonic_increasing:
        raise ValueError("Calendar must be nonempty, unique and chronological")
    df = bars.copy()
    df["date"] = daily_dates(df["date"])
    if df["ticker"].isna().any() or df["ticker"].astype(str).str.strip().eq("").any():
        raise ValueError("ticker must not be missing or empty")
    if df.duplicated(["ticker", "date"]).any():
        raise ValueError("Duplicate ticker/date")
    if not df["date"].isin(calendar).all():
        raise ValueError("Input dates outside exchange calendar")
    for col in ["RAW_SIGNAL", "is_st", "suspended", "limit_up_locked", "limit_down_locked"]:
        df[col] = strict_boolean(df[col], col)
    for col in ["amount", "listing_age_days"]:
        df[col] = finite_numeric(df[col], col)
    if (df["listing_age_days"] % 1 != 0).any():
        raise ValueError("listing_age_days must be integer trading-session counts")
    df = df.sort_values(["ticker", "date"]).reset_index(drop=True)
    # Require 20 consecutive calendar sessions; missing bars cannot be bridged.
    df["amt20"] = np.nan
    for _, group in df.groupby("ticker", sort=False):
        amounts = group.set_index("date")["amount"].reindex(calendar)
        rolling = amounts.rolling(20, min_periods=20).mean()
        df.loc[group.index, "amt20"] = rolling.reindex(group["date"]).to_numpy()
    signal = df["RAW_SIGNAL"]
    eligible = (~df["is_st"] & (df["listing_age_days"] >= min_listing_days) &
                (df["amt20"] >= min_turnover) & ~df["suspended"])
    df["EXECUTABLE_CANDIDATE"] = signal & eligible
    next_dates = pd.Series(calendar[1:], index=calendar[:-1])
    df["ENTRY_DATE"] = df["date"].map(next_dates)
    lookup = df.set_index(["ticker", "date"])
    keys = pd.MultiIndex.from_arrays([df["ticker"], df["ENTRY_DATE"]])
    next_rows = lookup.reindex(keys)
    df["ENTRY_SUSPENDED"] = next_rows["suspended"].to_numpy()
    df["ENTRY_LOCKED"] = next_rows["limit_up_locked"].to_numpy()
    present = pd.Series(keys.isin(lookup.index), index=df.index)
    possible = present & df["ENTRY_SUSPENDED"].eq(False) & df["ENTRY_LOCKED"].eq(False)
    candidate = df["EXECUTABLE_CANDIDATE"]
    df["ENTRY_STATUS"] = "NO_SIGNAL"
    df.loc[signal & ~eligible, "ENTRY_STATUS"] = "FILTERED_T"
    df.loc[candidate, "ENTRY_STATUS"] = "UNFILLED"
    df.loc[candidate & possible, "ENTRY_STATUS"] = "ELIGIBLE_FOR_FILL_CHECK"
    df.loc[candidate & ~present, "ENTRY_STATUS"] = "DATA_MISSING"
    df.loc[candidate & df["ENTRY_DATE"].isna(), "ENTRY_STATUS"] = "PENDING"
    return df
