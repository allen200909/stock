"""CSV/Parquet data loaders, deterministic synthetic generators, and QMT/PTADE scaffolds."""
from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

import numpy as np
import pandas as pd

from mbv.schema import (
    DataContractError,
    DataValidationError,
    DatasetMetadata,
    compute_dataframe_hash,
    validate_daily_bars,
)
from mbv.sessions import (
    Frequency,
    SHANGHAI_TZ,
    TimestampSemantics,
    expected_session_slots,
    normalize_bar_timestamps,
    validate_minute_bars,
)


def _read_table(path: str | Path) -> pd.DataFrame:
    p = Path(path)
    if not p.exists():
        raise FileNotFoundError(f"Input data file not found: {p}")
    suffix = p.suffix.lower()
    if suffix == ".csv":
        return pd.read_csv(p)
    if suffix in (".parquet", ".pq"):
        try:
            return pd.read_parquet(p)
        except ImportError as exc:
            raise DataContractError(
                "Parquet engine (pyarrow/fastparquet) is not installed in this offline environment; "
                "supply .csv or install pyarrow."
            ) from exc
    raise DataContractError(f"Unsupported file extension '{suffix}'; expected .csv or .parquet")


def write_table(df: pd.DataFrame, path: str | Path) -> Path:
    """Write DataFrame to CSV or Parquet; raises clear error if parquet engine is unavailable."""
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    suffix = p.suffix.lower()
    if suffix == ".csv":
        df.to_csv(p, index=False)
        return p
    if suffix in (".parquet", ".pq"):
        try:
            df.to_parquet(p, index=False)
            return p
        except ImportError as exc:
            raise DataContractError(
                "Parquet engine (pyarrow/fastparquet) is not installed in this offline environment; "
                "use .csv output path or install pyarrow."
            ) from exc
    raise DataContractError(f"Unsupported output extension '{suffix}'; expected .csv or .parquet")


def load_minute_bars(
    filepath: str | Path,
    *,
    frequency: Frequency = "5min",
    semantics: TimestampSemantics = "bar_start",
    tz: str = SHANGHAI_TZ,
    volume_unit: str = "share",
    amount_unit: str = "cny",
    adjustment: str = "unadjusted",
    source: str = "local_file",
    require_exchange_suffix: bool = False,
) -> tuple[pd.DataFrame, DatasetMetadata]:
    """Load, validate, and normalize minute bars from CSV or Parquet with provenance metadata."""
    raw = _read_table(filepath)
    validated = validate_minute_bars(
        raw,
        semantics=semantics,
        frequency=frequency,
        tz=tz,
        volume_unit=volume_unit,
        amount_unit=amount_unit,
        require_exchange_suffix=require_exchange_suffix,
    )
    meta = DatasetMetadata(
        source=source,
        frequency=frequency,
        timezone=tz,
        timestamp_semantics=semantics,
        volume_unit="share",
        amount_unit="cny",
        adjustment=adjustment,
        ingestion_time=datetime.now(timezone.utc).isoformat(),
        source_hash=compute_dataframe_hash(validated),
    )
    return validated, meta


def load_daily_bars(
    filepath: str | Path,
    *,
    volume_unit: str = "share",
    amount_unit: str = "cny",
) -> pd.DataFrame:
    """Load and validate daily OHLCV (+ optional point-in-time flags) from CSV or Parquet."""
    raw = _read_table(filepath)
    if volume_unit == "lot_100":
        raw = raw.copy()
        raw["volume"] = pd.to_numeric(raw["volume"], errors="raise").astype(float) * 100.0
    elif volume_unit != "share":
        raise DataContractError(f"Unsupported daily volume_unit '{volume_unit}'")
    if "amount" in raw.columns and not raw["amount"].isna().all():
        if amount_unit == "cny_10k":
            raw = raw.copy()
            raw["amount"] = pd.to_numeric(raw["amount"], errors="raise").astype(float) * 10000.0
        elif amount_unit != "cny":
            raise DataContractError(f"Unsupported daily amount_unit '{amount_unit}'")
    return validate_daily_bars(raw)


def generate_synthetic_market_bundle(
    *,
    symbols: tuple[str, ...] = ("600000.SH", "000001.SZ", "300750.SZ"),
    n_sessions: int = 165,
    minute_tail_sessions: int = 45,
    frequency: Frequency = "5min",
    seed: int = 20261111,
) -> dict[str, pd.DataFrame]:
    """Generate a deterministic, contract-compliant synthetic A-share dataset (SYNTHETIC_DEMO).

    - Generates `n_sessions` business days (avoiding weekends & Jan 1 holiday) so VLR B0 (`warm_n=145`)
      warms up cleanly and emits real B0 events (`EU`, `ABU`, `VU`, etc.).
    - Generates valid `frequency` (default 5min -> 48 bars/session, no 11:30-13:00 lunch bars)
      for the trailing `minute_tail_sessions` sessions, leaving earlier B0 sessions without minute
      data so left-join `MISSING_MINUTE_DATA` handling is naturally exercised too.
    - Guarantees `low <= min(open, close) <= max(open, close) <= high`, `prices > 0`, `volume >= 0`,
      and exact minute-to-daily volume reconciliation on normal days.
    """
    rng = np.random.default_rng(seed)
    raw_bdays = pd.bdate_range("2025-02-10", periods=n_sessions + 15)
    # Exclude Jan 1 / May 1 / Oct 1 fixed dates so synthetic sessions avoid obvious holiday dates
    valid_dates = [
        d for d in raw_bdays
        if not ((d.month == 1 and d.day == 1) or (d.month == 5 and d.day == 1) or (d.month == 10 and d.day == 1))
    ][:n_sessions]
    calendar_df = pd.DataFrame({"trade_date": [d.strftime("%Y-%m-%d") for d in valid_dates]})

    slots = expected_session_slots(frequency, exclude_closing_auction=False)
    u_shape = np.linspace(-1.0, 1.0, len(slots))
    intraday_profile = 1.0 + 0.65 * (u_shape ** 2)
    intraday_profile = intraday_profile / intraday_profile.sum()

    daily_rows: list[dict] = []
    minute_rows: list[dict] = []
    minute_start_idx = max(0, n_sessions - minute_tail_sessions)

    for sym_idx, symbol in enumerate(symbols):
        price = 20.0 + 10.0 * sym_idx
        base_daily_vol = 2_400_000.0 * (1.0 + 0.3 * sym_idx)

        for d_idx, dt in enumerate(valid_dates):
            d_str = dt.strftime("%Y-%m-%d")
            # Regime injection after B0 warmup (d_idx >= 146) to create EU / ABU / VU / normal days
            vol_mult = float(rng.lognormal(mean=0.0, sigma=0.22))
            drift = float(rng.normal(0.0, 0.009))
            burst_mode = "none"

            if d_idx >= 146:
                mod = (d_idx + 3 * sym_idx) % 9
                if mod == 0:
                    # Strong expansion up candidate (EU) with concentrated bullish microbursts
                    vol_mult = 2.15
                    drift = 0.042
                    burst_mode = "bull_concentrated"
                elif mod == 2:
                    # Strong expansion up candidate (EU) with uniform volume (no microbursts)
                    vol_mult = 2.05
                    drift = 0.038
                    burst_mode = "uniform_high"
                elif mod == 4:
                    # Absorption candidate (ABU): high volume, small daily range, offsetting bursts
                    vol_mult = 2.35
                    drift = 0.004
                    burst_mode = "offsetting"
                elif mod == 6:
                    # Vacuum up candidate (VU): low volume, large positive move
                    vol_mult = 0.85
                    drift = 0.036
                    burst_mode = "isolated_single"

            if d_idx < minute_start_idx:
                o = round(price * (1.0 + float(rng.normal(0.0, 0.002))), 2)
                c = round(max(1.0, o * (1.0 + drift)), 2)
                span = max(abs(c - o) * float(rng.uniform(1.15, 1.65)), 0.08)
                if burst_mode == "offsetting":
                    span = max(abs(c - o) * 1.15, 0.05)
                mid = 0.5 * (o + c)
                h = round(max(o, c, mid + 0.5 * span), 2)
                l = round(max(0.5, min(o, c, mid - 0.5 * span)), 2)
                v = float(round(base_daily_vol * vol_mult, -2))
                amt = round(v * 0.5 * (o + c), 2)
                price = c
            else:
                # Construct valid intraday bars first, then derive exact daily OHLCVA
                slot_vols = base_daily_vol * vol_mult * intraday_profile * rng.uniform(0.88, 1.12, size=len(slots))
                slot_rets = rng.normal(drift / len(slots), 0.0018, size=len(slots))

                if burst_mode == "bull_concentrated":
                    for b_slot in (3, 12, 38):
                        slot_vols[b_slot] *= 5.2
                        slot_rets[b_slot] = 0.0095
                elif burst_mode == "offsetting":
                    slot_vols[6] *= 4.8
                    slot_rets[6] = 0.0065
                    slot_vols[28] *= 4.9
                    slot_rets[28] = -0.0062
                elif burst_mode == "isolated_single":
                    slot_vols[42] *= 3.4
                    slot_rets[42] = 0.0075

                cur_p = price
                day_bars: list[dict] = []
                for s_idx, slot_t in enumerate(slots):
                    bar_o = round(max(0.5, cur_p), 2)
                    bar_c = round(max(0.5, bar_o * (1.0 + float(slot_rets[s_idx]))), 2)
                    if burst_mode in ("bull_concentrated", "offsetting", "isolated_single") and (
                        (burst_mode == "bull_concentrated" and s_idx in (3, 12, 38))
                        or (burst_mode == "offsetting" and s_idx in (6, 28))
                        or (burst_mode == "isolated_single" and s_idx == 42)
                    ):
                        # Ensure |C - O| >= 0.25 * (H - L) on injected burst bars
                        diff = bar_c - bar_o
                        if abs(diff) < 0.04:
                            diff = 0.06 if slot_rets[s_idx] >= 0 else -0.06
                            bar_c = round(max(0.5, bar_o + diff), 2)
                        wick = round(max(0.01, 0.25 * abs(bar_c - bar_o)), 2)
                    else:
                        wick = round(max(0.01, float(rng.uniform(0.01, 0.05))), 2)

                    bar_h = round(max(bar_o, bar_c) + wick, 2)
                    bar_l = round(max(0.2, min(bar_o, bar_c) - wick), 2)
                    bar_v = float(max(100, int(round(slot_vols[s_idx] / 100.0)) * 100))
                    bar_amt = round(bar_v * 0.5 * (bar_o + bar_c), 2)
                    ts_str = f"{d_str} {slot_t.strftime('%H:%M:%S')}"
                    day_bars.append({
                        "symbol": symbol,
                        "ts": ts_str,
                        "open": bar_o,
                        "high": bar_h,
                        "low": bar_l,
                        "close": bar_c,
                        "volume": bar_v,
                        "amount": bar_amt,
                    })
                    cur_p = bar_c

                minute_rows.extend(day_bars)
                o = day_bars[0]["open"]
                c = day_bars[-1]["close"]
                h = max(b["high"] for b in day_bars)
                l = min(b["low"] for b in day_bars)
                v = float(sum(b["volume"] for b in day_bars))
                amt = round(sum(b["amount"] for b in day_bars), 2)
                price = c

            daily_rows.append({
                "symbol": symbol,
                "trade_date": d_str,
                "open": o,
                "high": h,
                "low": l,
                "close": c,
                "volume": v,
                "amount": amt,
                "suspended": False,
                "st_flag": False,
                "board": "MAIN" if not symbol.startswith("300") else "CHINEXT",
                "listing_age_sessions": 500 + d_idx,
                "price_limit_status": "NONE",
                "corp_action_flag": False,
            })

    return {
        "daily": pd.DataFrame(daily_rows),
        "minute": pd.DataFrame(minute_rows),
        "calendar": calendar_df,
    }


def load_synthetic_minute_data(
    filepath: Optional[str | Path] = None,
    *,
    frequency: Frequency = "1min",
    seed: int = 20261111,
) -> pd.DataFrame:
    """Load minute bars from `filepath` if it exists; otherwise generate valid A-share session bars.

    Fixes WIP P0 defects:
    - Respects `filepath` when pointing to an existing CSV/Parquet file.
    - Uses `'1min'`/`'5min'` (never deprecated `'T'`), skips Jan 1 holiday and 11:30-13:00 lunch break.
    - Enforces valid OHLC bounds (`low <= open, close <= high`) and positive prices.
    """
    if filepath is not None and Path(filepath).exists():
        df, _ = load_minute_bars(filepath, frequency=frequency)
        return df

    bundle = generate_synthetic_market_bundle(
        symbols=("600000.SH",),
        n_sessions=22,
        minute_tail_sessions=22,
        frequency=frequency,
        seed=seed,
    )
    validated = validate_minute_bars(bundle["minute"], semantics="bar_start", frequency=frequency)
    return validated
