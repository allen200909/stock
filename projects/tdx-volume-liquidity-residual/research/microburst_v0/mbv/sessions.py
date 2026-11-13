"""A-share trading session geometry, timestamp normalization, and unit conversion."""
from __future__ import annotations

from datetime import time
from typing import Literal

import pandas as pd

from mbv.schema import (
    MINUTE_REQUIRED_COLS,
    DataContractError,
    ensure_finite_numeric,
    ensure_nonmissing_symbol,
    ensure_valid_ohlc,
)

Frequency = Literal["1min", "5min"]
TimestampSemantics = Literal["bar_start", "bar_end"]

SHANGHAI_TZ = "Asia/Shanghai"


def expected_session_slots(
    frequency: Frequency = "5min",
    *,
    exclude_closing_auction: bool = False,
) -> tuple[time, ...]:
    """Return canonical bar_start clock times for a normal A-share trading day.

    Morning continuous session:   09:30 <= bar_start < 11:30
    Afternoon session:            13:00 <= bar_start < 15:00
    1min -> 240 slots (or 237 when 14:57-14:59 closing auction is excluded).
    5min -> 48 slots (or 47 when 14:55 slot containing closing auction is excluded).
    """
    if frequency == "1min":
        step = 1
    elif frequency == "5min":
        step = 5
    else:
        raise DataContractError(f"Unsupported frequency '{frequency}'; expected '1min' or '5min'")

    slots: list[time] = []
    # Morning: 09:30 .. 11:29 (1m) or 09:30 .. 11:25 (5m)
    for minutes in range(9 * 60 + 30, 11 * 60 + 30, step):
        slots.append(time(minutes // 60, minutes % 60))
    # Afternoon: 13:00 .. 14:59 (1m) or 13:00 .. 14:55 (5m)
    aft_end = (14 * 60 + 57) if (exclude_closing_auction and frequency == "1min") else (15 * 60)
    if exclude_closing_auction and frequency == "5min":
        aft_end = 14 * 60 + 55
    for minutes in range(13 * 60, aft_end, step):
        slots.append(time(minutes // 60, minutes % 60))
    return tuple(slots)


def expected_slot_count(
    frequency: Frequency = "5min",
    *,
    exclude_closing_auction: bool = False,
) -> int:
    return len(expected_session_slots(frequency, exclude_closing_auction=exclude_closing_auction))


def is_closing_auction_slot(slot: time, frequency: Frequency = "5min") -> bool:
    """Flag 14:57-15:00 closing call auction window."""
    if frequency == "1min":
        return time(14, 57) <= slot <= time(14, 59)
    if frequency == "5min":
        return slot == time(14, 55)
    raise DataContractError(f"Unsupported frequency '{frequency}'")


def normalize_bar_timestamps(
    ts_series: pd.Series,
    *,
    frequency: Frequency = "5min",
    semantics: TimestampSemantics = "bar_start",
    tz: str = SHANGHAI_TZ,
) -> pd.Series:
    """Normalize bar timestamps to Asia/Shanghai bar_start timestamps and reject ambiguity.

    - If input timestamps are tz-aware, converts to `tz` (Asia/Shanghai).
    - If input timestamps are tz-naive, localizes to `tz` (Asia/Shanghai).
    - If `semantics == 'bar_end'`, shifts timestamps backward by 1min or 5min to `bar_start`,
      first verifying no `bar_start`-only boundary markers (09:30 or 13:00) are mixed in.
    - If `semantics == 'bar_start'`, verifies no `bar_end`-only boundary markers (11:30 or 15:00)
      or lunch-gap / off-hours bars are present.
    """
    if frequency not in ("1min", "5min"):
        raise DataContractError(f"Unsupported frequency '{frequency}'; expected '1min' or '5min'")
    if semantics not in ("bar_start", "bar_end"):
        raise DataContractError(
            f"Ambiguous or unsupported timestamp semantics '{semantics}'; must be 'bar_start' or 'bar_end'"
        )
    if ts_series.isna().any():
        raise DataContractError("ts column contains null/NaN timestamps")

    try:
        parsed = pd.to_datetime(ts_series, errors="raise")
    except (ValueError, TypeError) as exc:
        raise DataContractError("Failed to parse minute timestamps in 'ts'") from exc

    dt_index = pd.DatetimeIndex(parsed)
    if dt_index.hasnans:
        raise DataContractError("ts column contains NaT values")

    if dt_index.tz is None:
        dt_index = dt_index.tz_localize(tz)
    else:
        dt_index = dt_index.tz_convert(tz)

    if (dt_index.second != 0).any() or (dt_index.microsecond != 0).any():
        raise DataContractError("Minute bar timestamps must align to exact minute boundaries (seconds == 0)")

    step_minutes = 1 if frequency == "1min" else 5
    if (dt_index.minute % step_minutes != 0).any():
        raise DataContractError(f"Timestamps do not align to {frequency} grid")

    raw_times = pd.Index(dt_index.time)

    if semantics == "bar_end":
        # Under bar_end semantics, 09:30 or 13:00 cannot be the end of a regular trading bar
        if raw_times.isin([time(9, 30), time(13, 0)]).any():
            raise DataContractError(
                "Timestamp semantics ambiguity: declared 'bar_end' but found 09:30 or 13:00 start boundary"
            )
        dt_index = dt_index - pd.Timedelta(minutes=step_minutes)
    else:
        # Under bar_start semantics, 11:30 or 15:00 cannot be the start of a regular trading bar
        if raw_times.isin([time(11, 30), time(15, 0)]).any():
            raise DataContractError(
                "Timestamp semantics ambiguity: declared 'bar_start' but found 11:30 or 15:00 end boundary"
            )

    valid_slots = set(expected_session_slots(frequency, exclude_closing_auction=False))
    norm_times = dt_index.time
    invalid_mask = [t not in valid_slots for t in norm_times]
    if any(invalid_mask):
        bad_pos = invalid_mask.index(True)
        bad_ts = dt_index[bad_pos]
        t_val = norm_times[bad_pos]
        if time(11, 30) <= t_val < time(13, 0):
            raise DataContractError(f"Lunch-break bar rejected at {bad_ts} (11:30-13:00 closed)")
        raise DataContractError(f"Off-session bar timestamp rejected at {bad_ts}")

    return pd.Series(dt_index, index=ts_series.index, name="ts")


def convert_units(
    df: pd.DataFrame,
    *,
    volume_unit: str = "share",
    amount_unit: str = "cny",
) -> pd.DataFrame:
    """Normalize volume to shares and amount (if present) to CNY."""
    out = df.copy()
    if volume_unit == "share":
        pass
    elif volume_unit == "lot_100":
        out["volume"] = out["volume"].astype(float) * 100.0
    else:
        raise DataContractError(
            f"Unsupported volume_unit '{volume_unit}'; expected 'share' or 'lot_100'"
        )

    if "amount" in out.columns and not out["amount"].isna().all():
        if amount_unit == "cny":
            pass
        elif amount_unit == "cny_10k":
            out["amount"] = out["amount"].astype(float) * 10000.0
        else:
            raise DataContractError(
                f"Unsupported amount_unit '{amount_unit}'; expected 'cny' or 'cny_10k'"
            )
    elif amount_unit not in ("cny", "cny_10k"):
        raise DataContractError(
            f"Unsupported amount_unit '{amount_unit}'; expected 'cny' or 'cny_10k'"
        )
    return out


def validate_minute_bars(
    df: pd.DataFrame,
    semantics: TimestampSemantics = "bar_start",
    *,
    frequency: Frequency = "5min",
    tz: str = SHANGHAI_TZ,
    volume_unit: str = "share",
    amount_unit: str = "cny",
    require_exchange_suffix: bool = False,
) -> pd.DataFrame:
    """Fail-closed validator & normalizer for intraday 1m/5m OHLCV bars.

    Checks enforced:
    1. Required columns present and non-empty DataFrame.
    2. Non-null, non-empty symbol (optional exchange-suffix check).
    3. Finite positive prices (`open, high, low, close > 0`) and valid OHLC bounds (`L <= O,C <= H`).
    4. Finite non-negative volume (`volume >= 0`, rejects negative, NaN, Inf).
    5. Timestamp normalization to `Asia/Shanghai` `bar_start`, rejecting 11:30-13:00 lunch bars,
       off-hours bars (e.g. 08:00, 15:05), and `bar_start`/`bar_end` boundary ambiguity.
    6. Strict `(symbol, ts)` uniqueness after normalization (no silent summing or deduplication).
    7. Unit normalization (`lot_100` -> `share`, `cny_10k` -> `cny`) and chronological sorting.
    """
    if df is None or df.empty:
        raise DataContractError("Minute bars DataFrame must not be empty")
    missing = [c for c in MINUTE_REQUIRED_COLS if c not in df.columns]
    if missing:
        raise DataContractError(f"Missing required minute columns: {missing}")

    out = df.copy()
    out["symbol"] = ensure_nonmissing_symbol(
        out["symbol"], require_exchange_suffix=require_exchange_suffix
    )

    for price_col in ("open", "high", "low", "close"):
        out[price_col] = ensure_finite_numeric(out[price_col], price_col, strictly_positive=True)
    out["volume"] = ensure_finite_numeric(out["volume"], "volume", non_negative=True)
    if "amount" in out.columns and not out["amount"].isna().all():
        out["amount"] = ensure_finite_numeric(out["amount"], "amount", non_negative=True)

    ensure_valid_ohlc(out)

    # Reject raw duplicate (symbol, ts) before normalization as well as after
    if out.duplicated(subset=["symbol", "ts"]).any():
        raise DataContractError("Duplicate (symbol, ts) minute records detected")

    out["ts"] = normalize_bar_timestamps(
        out["ts"], frequency=frequency, semantics=semantics, tz=tz
    )
    if out.duplicated(subset=["symbol", "ts"]).any():
        raise DataContractError("Duplicate (symbol, ts) minute records after timestamp normalization")

    out = convert_units(out, volume_unit=volume_unit, amount_unit=amount_unit)

    out["trade_date"] = out["ts"].dt.strftime("%Y-%m-%d")
    out["time_slot"] = out["ts"].dt.time
    out["closing_auction_window"] = [
        is_closing_auction_slot(s, frequency=frequency) for s in out["time_slot"]
    ]
    out = out.sort_values(["symbol", "ts"]).reset_index(drop=True)
    return out
