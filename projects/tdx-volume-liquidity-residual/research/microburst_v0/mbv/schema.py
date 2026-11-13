"""Data contracts, provenance metadata, and strict input validators for MBV V0.1."""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
import hashlib
from typing import Any, Optional

import numpy as np
import pandas as pd


class DataContractError(ValueError):
    """Raised when minute, daily, or join inputs violate the MBV V0.1 data contract."""


DataValidationError = DataContractError


MINUTE_REQUIRED_COLS = ("symbol", "ts", "open", "high", "low", "close", "volume")
DAILY_REQUIRED_COLS = ("symbol", "trade_date", "open", "high", "low", "close", "volume")

DAILY_OPTIONAL_STATE_COLS = (
    "suspended",
    "st_flag",
    "board",
    "listing_age_sessions",
    "price_limit_status",
    "corp_action_flag",
)

MBV_DAILY_FEATURE_COLS = (
    "symbol",
    "trade_date",
    "burst_count",
    "burst_share",
    "peak_ratio",
    "burst_dominance",
    "burst_concentration",
    "single_burst_flag",
    "burst_direction_agreement",
    "valid_slot_coverage",
    "baseline_slot_coverage",
    "minute_total_volume",
    "vol_recon_error",
    "vol_recon_status",
    "burst_regime",
    "feature_status",
)

FORBIDDEN_FUTURE_PREFIXES = ("fwd_ret", "forward_return", "future_ret", "mfe_", "mae_", "next_ret")


@dataclass(frozen=True)
class MinuteBar:
    symbol: str
    ts: str
    open: float
    high: float
    low: float
    close: float
    volume: float
    amount: Optional[float] = None


@dataclass(frozen=True)
class DailyFeature:
    symbol: str
    trade_date: str
    burst_count: float
    burst_share: float
    peak_ratio: float
    burst_dominance: float
    burst_concentration: float
    single_burst_flag: bool
    burst_direction_agreement: float
    valid_slot_coverage: float
    baseline_slot_coverage: float
    vol_recon_error: float
    burst_regime: str
    feature_status: str


@dataclass(frozen=True)
class DatasetMetadata:
    source: str
    source_version: str = "0.1.0"
    frequency: str = "5min"
    timezone: str = "Asia/Shanghai"
    timestamp_semantics: str = "bar_start"
    volume_unit: str = "share"
    amount_unit: str = "cny"
    adjustment: str = "unadjusted"
    ingestion_time: str = field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )
    source_hash: str = ""


def compute_dataframe_hash(df: pd.DataFrame) -> str:
    """Deterministic SHA256 fingerprint of a DataFrame's columns and values."""
    csv_bytes = df.to_csv(index=False).encode("utf-8")
    return hashlib.sha256(csv_bytes).hexdigest()[:16]


def compute_params_hash(params: dict[str, Any]) -> str:
    """Deterministic SHA256 fingerprint of configuration parameters."""
    canonical = repr(sorted(params.items())).encode("utf-8")
    return hashlib.sha256(canonical).hexdigest()[:16]


def ensure_nonmissing_symbol(series: pd.Series, *, require_exchange_suffix: bool = False) -> pd.Series:
    if series.isna().any():
        raise DataContractError("symbol column contains null/NaN values")
    cleaned = series.astype(str).str.strip()
    if (cleaned == "").any() or cleaned.isin(["nan", "None", "<NA>"]).any():
        raise DataContractError("symbol column contains empty or stringified null values")
    if require_exchange_suffix:
        bad = ~cleaned.str.contains(r"\.[A-Za-z]{2,}$", regex=True)
        if bad.any():
            sample = cleaned[bad].iloc[0]
            raise DataContractError(
                f"symbol must carry exchange suffix (e.g. 600000.SH), got '{sample}'"
            )
    return cleaned


def ensure_finite_numeric(
    series: pd.Series,
    col_name: str,
    *,
    strictly_positive: bool = False,
    non_negative: bool = False,
) -> pd.Series:
    if series.isna().any():
        raise DataContractError(f"{col_name} contains NaN/null values")
    try:
        num = pd.to_numeric(series, errors="raise").astype(float)
    except (ValueError, TypeError) as exc:
        raise DataContractError(f"{col_name} must be numeric") from exc
    arr = num.to_numpy(dtype=float)
    if not np.isfinite(arr).all():
        raise DataContractError(f"{col_name} contains non-finite (inf/-inf/NaN) values")
    if strictly_positive and (arr <= 0).any():
        raise DataContractError(f"{col_name} must be strictly positive (> 0)")
    if non_negative and (arr < 0).any():
        raise DataContractError(f"{col_name} must be non-negative (>= 0), negative volume/amount rejected")
    return num


def ensure_valid_ohlc(df: pd.DataFrame) -> None:
    o = df["open"].to_numpy(dtype=float)
    h = df["high"].to_numpy(dtype=float)
    l = df["low"].to_numpy(dtype=float)
    c = df["close"].to_numpy(dtype=float)
    upper = np.maximum(np.maximum(o, c), l)
    lower = np.minimum(np.minimum(o, c), h)
    if (h < upper - 1e-12).any() or (l > lower + 1e-12).any():
        raise DataContractError("Inconsistent OHLC bounds: require low <= open,close <= high")


def normalize_trade_date(series: pd.Series, col_name: str = "trade_date") -> pd.Series:
    if series.isna().any():
        raise DataContractError(f"{col_name} contains null/NaN values")
    try:
        dt = pd.to_datetime(series, errors="raise")
    except (ValueError, TypeError) as exc:
        raise DataContractError(f"Invalid date values in {col_name}") from exc
    idx = pd.DatetimeIndex(dt)
    if idx.hasnans:
        raise DataContractError(f"{col_name} contains unparseable dates")
    if idx.tz is not None:
        raise DataContractError(f"{col_name} must be timezone-naive daily dates")
    if not idx.equals(idx.normalize()):
        raise DataContractError(f"{col_name} must not carry intraday clock offsets")
    return pd.Series(idx.strftime("%Y-%m-%d"), index=series.index, name=col_name)


def assert_no_future_columns(df: pd.DataFrame) -> None:
    """Guard T17: T-day feature / joined tables must never contain forward-return columns."""
    leaked = [
        c for c in df.columns
        if any(str(c).lower().startswith(prefix) for prefix in FORBIDDEN_FUTURE_PREFIXES)
    ]
    if leaked:
        raise DataContractError(
            f"Forward-looking outcome columns forbidden in T-day feature table: {leaked}"
        )


def validate_daily_bars(df: pd.DataFrame) -> pd.DataFrame:
    """Validate daily OHLCV + optional point-in-time corporate/limit status columns."""
    if df is None or df.empty:
        raise DataContractError("Daily bars DataFrame must not be empty")
    missing = [c for c in DAILY_REQUIRED_COLS if c not in df.columns]
    if missing:
        raise DataContractError(f"Missing required daily columns: {missing}")

    out = df.copy()
    out["symbol"] = ensure_nonmissing_symbol(out["symbol"])
    out["trade_date"] = normalize_trade_date(out["trade_date"], "trade_date")

    if out.duplicated(subset=["symbol", "trade_date"]).any():
        raise DataContractError("Duplicate (symbol, trade_date) keys in daily data")

    for price_col in ("open", "high", "low", "close"):
        out[price_col] = ensure_finite_numeric(out[price_col], price_col, strictly_positive=True)
    out["volume"] = ensure_finite_numeric(out["volume"], "volume", non_negative=True)
    if "amount" in out.columns and not out["amount"].isna().all():
        out["amount"] = ensure_finite_numeric(out["amount"], "amount", non_negative=True)

    # Allow suspended days to have volume == 0, otherwise require OHLC consistency on all rows
    ensure_valid_ohlc(out)
    out = out.sort_values(["symbol", "trade_date"]).reset_index(drop=True)
    return out
