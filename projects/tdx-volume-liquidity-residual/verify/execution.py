"""A-share long-only execution research layer (historical flags required).

Inputs are point-in-time per-day data with columns:
date, ticker, RAW_SIGNAL, amount, is_st, listing_age_days, suspended,
limit_up_locked, limit_down_locked; optionally next_open_locked.
Records actual entry attempt on next observed trading date per ticker.
Absence of required historical flags fails closed, never guesses board rules.
"""
from __future__ import annotations

import pandas as pd

REQUIRED = {
    "date","ticker","RAW_SIGNAL","amount","is_st","listing_age_days",
    "suspended","limit_up_locked","limit_down_locked",
}

def build_execution_table(bars:pd.DataFrame, *, min_turnover=50_000_000,
                          min_listing_days=250) -> pd.DataFrame:
    missing=REQUIRED-set(bars.columns)
    if missing:
        raise ValueError(f"Missing point-in-time columns: {sorted(missing)}")
    df=bars.copy().sort_values(["ticker","date"]).reset_index(drop=True)
    # Avoid using future bars in today's raw signal or candidate decision.
    df["amt20"]=df.groupby("ticker")["amount"].transform(
        lambda s:s.rolling(20,min_periods=20).mean())
    signal=df["RAW_SIGNAL"].astype(bool)
    eligible=(~df["is_st"].astype(bool)) & (
        df["listing_age_days"]>=min_listing_days) & (
        df["amt20"]>=min_turnover) & (~df["suspended"].astype(bool))
    df["EXECUTABLE_CANDIDATE"]=signal & eligible
    grp=df.groupby("ticker",sort=False)
    df["ENTRY_DATE"]=grp["date"].shift(-1)
    # Next-session conditions are execution outcomes, NOT T-day selectors.
    df["ENTRY_SUSPENDED"]=grp["suspended"].shift(-1)
    df["ENTRY_LOCKED"]=grp["limit_up_locked"].shift(-1)
    entry_possible=(df["ENTRY_DATE"].notna() &
                    df["ENTRY_SUSPENDED"].eq(False) &
                    df["ENTRY_LOCKED"].eq(False))
    df["ENTRY_STATUS"]="NO_SIGNAL"
    df.loc[signal & ~eligible,"ENTRY_STATUS"]="FILTERED_T"
    df.loc[df["EXECUTABLE_CANDIDATE"] & ~entry_possible,
           "ENTRY_STATUS"]="UNFILLED"
    df.loc[df["EXECUTABLE_CANDIDATE"] & entry_possible,
           "ENTRY_STATUS"]="ELIGIBLE_FOR_FILL_CHECK"
    # Cannot declare filled without OHLC quotes, queue and order simulation.
    return df

