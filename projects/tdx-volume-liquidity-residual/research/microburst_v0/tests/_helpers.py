"""Shared deterministic fixture builders for the R6 test-suite (no randomness without explicit seeds)."""
from __future__ import annotations

from datetime import time
from typing import Callable, Optional

import numpy as np
import pandas as pd

from mbv.sessions import expected_session_slots, validate_minute_bars


def bdays(n: int, start: str = "2026-01-05") -> list[str]:
    return [d.strftime("%Y-%m-%d") for d in pd.bdate_range(start, periods=n)]


def make_panel(
    symbols: list[str],
    dates: list[str],
    vol_fn: Callable[[str, int, int], float],
    *,
    frequency: str = "5min",
    body_fn: Optional[Callable[[str, int, int], float]] = None,
    skip_fn: Optional[Callable[[str, int, int], bool]] = None,
    validate: bool = True,
) -> pd.DataFrame:
    """Build a contract-compliant minute panel.

    ``body_fn`` returns the signed candle body (close - open) in price units on a 0.30 range bar
    (default +0.15 -> body efficiency +0.5). ``skip_fn`` drops bars to simulate missing minute data.
    """
    slots = expected_session_slots(frequency)
    rows = []
    for sym in symbols:
        for d_idx, d_str in enumerate(dates):
            for s_idx, slot_t in enumerate(slots):
                if skip_fn is not None and skip_fn(sym, d_idx, s_idx):
                    continue
                body = 0.15 if body_fn is None else float(body_fn(sym, d_idx, s_idx))
                o = 10.00
                c = round(o + body, 4)
                h = max(o, c) + max(0.0, (0.30 - abs(body)) / 2)
                l = min(o, c) - max(0.0, (0.30 - abs(body)) / 2)
                rows.append({
                    "symbol": sym,
                    "ts": f"{d_str} {slot_t.strftime('%H:%M:%S')}",
                    "open": o, "high": round(h, 4), "low": round(l, 4), "close": c,
                    "volume": float(vol_fn(sym, d_idx, s_idx)),
                })
    raw = pd.DataFrame(rows)
    if not validate:
        return raw
    return validate_minute_bars(raw, semantics="bar_start", frequency=frequency)


def burst_rows(
    symbol: str,
    trade_date: str,
    spec: dict[int, dict],
    *,
    frequency: str = "5min",
    normal_volume: float = 100.0,
    normal_baseline: float = 100.0,
    drop_slots: tuple[int, ...] = (),
) -> pd.DataFrame:
    """Hand-built per-bar detect_bursts-like rows for direct aggregation tests.

    Every canonical slot gets volume=normal_volume, baseline=normal_baseline, efficiency 0.05 (not a burst)
    unless overridden in ``spec[slot_index] = {volume, baseline, rel_vol, body_efficiency, is_burst}``.
    """
    slots = expected_session_slots(frequency)
    out = []
    for k, slot_t in enumerate(slots):
        if k in drop_slots:
            continue
        rec = {
            "symbol": symbol, "trade_date": trade_date, "time_slot": slot_t,
            "volume": normal_volume, "baseline": normal_baseline,
            "rel_vol": normal_volume / normal_baseline if normal_baseline else np.nan,
            "body_efficiency": 0.05, "is_burst": False,
        }
        rec.update(spec.get(k, {}))
        if "rel_vol" not in spec.get(k, {}) and rec["baseline"] and np.isfinite(rec["baseline"]):
            rec["rel_vol"] = rec["volume"] / rec["baseline"]
        out.append(rec)
    return pd.DataFrame(out)


def slot_index(t: str, frequency: str = "5min") -> int:
    hh, mm = (int(x) for x in t.split(":"))
    return list(expected_session_slots(frequency)).index(time(hh, mm))
