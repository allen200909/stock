"""Data adapter scaffolds for local CSV/Parquet and optional broker terminals (QMT / PTrade).

No proprietary SDK methods are fabricated: when `xtquant` or PTrade offline exports are absent,
these adapters fail closed with `BLOCKED_REAL_DATA` diagnostic statuses.
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

import pandas as pd

from mbv.adapters import load_daily_bars, load_minute_bars
from mbv.schema import DatasetMetadata


@dataclass(frozen=True)
class BrokerProbeResult:
    provider: str
    available: bool
    status: str
    detail: str


def probe_qmt_environment() -> BrokerProbeResult:
    """Probe whether `xtquant.xtdata` is importable in the current Python runtime."""
    try:
        import importlib
        importlib.import_module("xtquant.xtdata")
        return BrokerProbeResult(
            provider="QMT_xtquant",
            available=True,
            status="SDK_IMPORTABLE_DATA_UNVERIFIED",
            detail="xtquant.xtdata found; export sample and run inspect-data before research use.",
        )
    except ImportError:
        return BrokerProbeResult(
            provider="QMT_xtquant",
            available=False,
            status="BLOCKED_REAL_DATA",
            detail="xtquant SDK not installed in offline environment; use exported CSV/Parquet via load_minute_bars.",
        )


def probe_ptrade_environment(export_dir: str | Path | None = None) -> BrokerProbeResult:
    """Check whether verified PTrade offline minute exports exist at `export_dir`."""
    if export_dir is None or not Path(export_dir).exists():
        return BrokerProbeResult(
            provider="PTrade_export",
            available=False,
            status="BLOCKED_REAL_DATA",
            detail="No local PTrade export directory supplied or directory does not exist.",
        )
    files = list(Path(export_dir).glob("*.csv")) + list(Path(export_dir).glob("*.parquet"))
    if not files:
        return BrokerProbeResult(
            provider="PTrade_export",
            available=False,
            status="BLOCKED_REAL_DATA",
            detail=f"Directory {export_dir} contains no CSV/Parquet files.",
        )
    return BrokerProbeResult(
        provider="PTrade_export",
        available=True,
        status="FILES_FOUND_PENDING_RECONCILIATION",
        detail=f"Found {len(files)} candidate file(s); run mbv.cli inspect-data to verify contract.",
    )


def load_local_research_bundle(
    minute_path: str | Path,
    daily_path: str | Path,
    *,
    config: dict[str, Any],
) -> tuple[pd.DataFrame, pd.DataFrame, DatasetMetadata]:
    dc = config.get("data_contract", {})
    min_df, meta = load_minute_bars(
        minute_path,
        frequency=dc.get("frequency", "5min"),
        semantics=dc.get("timestamp_semantics", "bar_start"),
        tz=dc.get("timezone", "Asia/Shanghai"),
        volume_unit=dc.get("volume_unit", "share"),
        amount_unit=dc.get("amount_unit", "cny"),
        adjustment=dc.get("adjustment", "unadjusted"),
    )
    day_df = load_daily_bars(
        daily_path,
        volume_unit=dc.get("volume_unit", "share"),
        amount_unit=dc.get("amount_unit", "cny"),
    )
    return min_df, day_df, meta
