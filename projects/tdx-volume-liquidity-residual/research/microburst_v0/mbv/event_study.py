"""Event study, matched/permutation controls, T+1 forward outcomes, and block bootstrap wrapper.

R6 (WP-C) changes on top of Carbon R5:
- Group E permutation now permutes MBV features ONLY within frozen RVOL buckets of ``B0_RVRAW``
  (bucket sizes preserved), reports seed / permutations / per-bucket counts / two-sided p-value and returns
  ``INCONCLUSIVE`` when RVOL is unavailable or no bucket is permutable.
- Matched controls use an explicit ``board_policy`` (default ``strict``); board relaxation is only possible via
  ``relax_explicit`` and is counted, never silent. Treated rows without RVOL bucket are unmatched and counted.
- T+1 outcomes keep data-missing (``DATA_MISSING``) and non-fillable (``UNFILLED_*``) states distinct, add
  ``UNFILLED_LIMIT_UP_T1`` from point-in-time limit status, and never assert open fill from daily OHLC alone:
  without status columns rows are labelled ``TRADABILITY_UNVERIFIED_T1`` (hypothetical return only).
- Bootstrap reports seed, block-length sensitivity, dropped long blocks and events dropped for missing returns.
- Study result carries an explicit research ``conclusion`` and gate status; synthetic output is never evidence.

R7 (design decisions 2026-11-12):
- Study mode / exchange calendar / pre-registration are resolved by ``mbv.calendar_policy.resolve_study_context``;
  formal modes require a verified exchange calendar bound by SHA-256 to the MBV feature stamps.
- T+1 classification no longer treats ``LIMIT_UP + open>=high`` as proof of an unfilled order
  (``OPEN_LIMIT_UP_FILL_UNVERIFIED_T1``); status is trusted only with ``tradability_status_source``; actual
  unfilled / filled requires order or order-book evidence. Hypothetical returns (``fwd_ret_*``) and
  confirmed-executable returns (``exec_ret_*``) are stored separately.
"""
from __future__ import annotations

from pathlib import Path
import sys
from typing import Any, Optional, Sequence

import numpy as np
import pandas as pd

from mbv.calendar_policy import (
    VALID_STUDY_LABELS,
    assert_dates_in_preregistered_window,
    assert_feature_calendar_consistent,
    resolve_study_context,
)
from mbv.join import resolve_vlr_verify_dir
from mbv.schema import DataContractError, assert_no_future_columns, normalize_trade_date
VALID_BOARD_POLICIES = ("strict", "relax_explicit", "ignore")

# Gate status that no offline/synthetic run can upgrade (handoff §3 WP-D / §6).
GATE_STATUS = {
    "G1_REAL_MINUTE_DATA": "BLOCKED_REAL_DATA",
    "G2_TDX_B0_PARITY": "NOT_VERIFIED",
    "G3_REAL_EVENT_STUDY": "NOT_TESTED",
}

T1_LIMIT_UP_TOKENS = ("LIMIT_UP", "LOCKED_UP")


def _bool_series(df: pd.DataFrame, col: str) -> pd.Series:
    """Missing column / NaN -> False without pandas object-downcasting FutureWarnings."""
    if col not in df.columns:
        return pd.Series(False, index=df.index, dtype=bool)
    return df[col].map(lambda v: bool(v) if pd.notna(v) else False).astype(bool)


def validate_trading_calendar(trading_calendar: Optional[Sequence[Any] | pd.Series | pd.DataFrame]) -> list[str]:
    """Fail-closed exchange calendar gate (T16): refuse formal T+1 study when calendar is missing."""
    if trading_calendar is None:
        raise DataContractError(
            "Explicit trading_calendar is required for forward-return / T+1 event study (T16 fail-closed)"
        )
    if isinstance(trading_calendar, pd.DataFrame):
        if "trade_date" not in trading_calendar.columns:
            raise DataContractError("Calendar DataFrame must contain 'trade_date' column")
        raw = trading_calendar["trade_date"]
    else:
        raw = pd.Series(list(trading_calendar))

    if raw.empty:
        raise DataContractError("trading_calendar must not be empty")
    norm = normalize_trade_date(raw.reset_index(drop=True), "trading_calendar")
    if norm.duplicated().any():
        raise DataContractError("trading_calendar must contain unique trading dates")
    if not norm.is_monotonic_increasing:
        raise DataContractError("trading_calendar must be sorted chronologically")
    return norm.tolist()


RETURN_BASIS_HYPOTHETICAL = "HYPOTHETICAL_T1_OPEN_PRICE"

# R7: T+1 fill status -> execution class. Hypothetical (T+1 open price) returns are kept for factor research on
# every class except NO_DATA and status-confirmed non-executable sessions; ``exec_ret_*`` (confirmed-executable
# return statistics) is populated ONLY for CONFIRMED_FILLED and STATUS_CHECKED_EXECUTABLE rows.
T1_STATUS_CLASS = {
    "PENDING_FUTURE_SESSION": "NO_DATA",
    "DATA_MISSING": "NO_DATA",
    "SUSPENDED_T1_STATUS_CONFIRMED": "NOT_EXECUTABLE_CONFIRMED",
    "TRADING_RESTRICTED_T1_STATUS_CONFIRMED": "NOT_EXECUTABLE_CONFIRMED",
    "ZERO_VOLUME_T1": "NOT_EXECUTABLE_CONFIRMED",
    "UNFILLED_T1_ORDER_EVIDENCE": "NOT_EXECUTABLE_CONFIRMED",
    "OPEN_LIMIT_UP_FILL_UNVERIFIED_T1": "FILL_UNVERIFIED",
    "TRADABILITY_UNVERIFIED_T1": "FILL_UNVERIFIED",
    "ELIGIBLE_T1_OPEN_STATUS_CHECKED": "STATUS_CHECKED_EXECUTABLE",
    "FILLED_T1_ORDER_EVIDENCE": "CONFIRMED_FILLED",
}
EXECUTABLE_CLASSES = ("CONFIRMED_FILLED", "STATUS_CHECKED_EXECUTABLE")
_NO_HYPOTHETICAL_RETURN = ("PENDING_FUTURE_SESSION", "DATA_MISSING", "SUSPENDED_T1_STATUS_CONFIRMED",
                           "TRADING_RESTRICTED_T1_STATUS_CONFIRMED", "ZERO_VOLUME_T1")
EVIDENCE_TYPES = ("ORDER", "ORDER_BOOK")
EVIDENCE_FILL_STATUSES = ("FILLED", "NOT_FILLED")
EVIDENCE_REQUIRED_COLS = ("symbol", "entry_date", "evidence_type", "fill_status", "fill_price", "evidence_source")


def _flag(row: pd.Series, col: str) -> Optional[bool]:
    """Tri-state status value: None when the column is absent / NaN."""
    if col not in row.index or pd.isna(row[col]):
        return None
    return bool(row[col])


def trusted_status_source(row: pd.Series) -> Optional[str]:
    """Point-in-time status columns are trusted only with a declared, non-synthetic ``tradability_status_source``."""
    if "tradability_status_source" not in row.index or pd.isna(row["tradability_status_source"]):
        return None
    src = str(row["tradability_status_source"]).strip()
    if not src or src.upper().startswith("SYNTHETIC"):
        return None
    return src


def validate_execution_evidence(evidence: Optional[pd.DataFrame]) -> dict[tuple[str, str], dict[str, Any]]:
    """Order / order-book evidence table -> {(symbol, entry_date): record}. Fail-closed on any ambiguity."""
    if evidence is None:
        return {}
    missing = [c for c in EVIDENCE_REQUIRED_COLS if c not in evidence.columns]
    if missing:
        raise DataContractError(f"Execution evidence missing columns {missing}")
    if evidence.empty:
        return {}
    ev = evidence.copy()
    ev["symbol"] = ev["symbol"].astype(str).str.strip()
    ev["entry_date"] = normalize_trade_date(ev["entry_date"].reset_index(drop=True), "entry_date").to_numpy()
    if ev.duplicated(subset=["symbol", "entry_date"]).any():
        raise DataContractError("Duplicate (symbol, entry_date) keys in execution evidence")
    out: dict[tuple[str, str], dict[str, Any]] = {}
    for _, r in ev.iterrows():
        etype = str(r["evidence_type"]).strip().upper()
        fstat = str(r["fill_status"]).strip().upper()
        src = "" if pd.isna(r["evidence_source"]) else str(r["evidence_source"]).strip()
        if etype not in EVIDENCE_TYPES:
            raise DataContractError(f"evidence_type must be one of {EVIDENCE_TYPES}, got {r['evidence_type']!r}")
        if fstat not in EVIDENCE_FILL_STATUSES:
            raise DataContractError(f"fill_status must be one of {EVIDENCE_FILL_STATUSES}, got {r['fill_status']!r}")
        if not src:
            raise DataContractError("evidence_source must be non-empty for every execution evidence row")
        price = pd.to_numeric(pd.Series([r["fill_price"]]), errors="coerce").iloc[0]
        if fstat == "FILLED" and not (pd.notna(price) and float(price) > 0.0):
            raise DataContractError("FILLED execution evidence requires a positive fill_price")
        out[(r["symbol"], r["entry_date"])] = {
            "evidence_type": etype, "fill_status": fstat, "evidence_source": src,
            "fill_price": float(price) if pd.notna(price) else np.nan,
        }
    return out


def _t1_tradability(t1_row: pd.Series, evidence: Optional[dict[str, Any]] = None) -> dict[str, Any]:
    """Classify T+1 open executability (R7). ``LIMIT_UP + open>=high`` is a conservative exclusion only.

    Returns dict(fill_status, status_source, evidence_source, risk_flags, fill_price).
    """
    t1_vol = float(t1_row["volume"])
    src = trusted_status_source(t1_row)
    suspended = _flag(t1_row, "suspended")
    restricted = _flag(t1_row, "trading_restricted")
    lim = (str(t1_row["price_limit_status"]).upper()
           if "price_limit_status" in t1_row.index and pd.notna(t1_row["price_limit_status"]) else None)
    open_at_limit_up = lim in T1_LIMIT_UP_TOKENS and float(t1_row["open"]) >= float(t1_row["high"])
    flags: list[str] = []
    if float(t1_row["high"]) == float(t1_row["low"]):
        flags.append("ONE_WORD_LOCKED")
    if open_at_limit_up:
        flags.append("OPEN_AT_LIMIT_UP")
    raw_src = ("" if "tradability_status_source" not in t1_row.index or pd.isna(t1_row["tradability_status_source"])
               else str(t1_row["tradability_status_source"]).strip())

    def _res(status: str, status_source: str, ev_src: Optional[str] = None, price: float = np.nan) -> dict[str, Any]:
        return {"fill_status": status, "status_source": status_source, "evidence_source": ev_src,
                "risk_flags": "|".join(flags) if flags else "NONE", "fill_price": price}

    if evidence is not None:
        if evidence["fill_status"] == "FILLED" and (t1_vol <= 0.0 or (src is not None and (suspended or restricted))):
            raise DataContractError(
                "FILLED execution evidence contradicts confirmed suspension / restriction / zero volume on "
                f"{t1_row.name}"
            )
        ev_status_source = f"ORDER_EVIDENCE:{evidence['evidence_type']}"
        if evidence["fill_status"] == "FILLED":
            return _res("FILLED_T1_ORDER_EVIDENCE", ev_status_source, evidence["evidence_source"],
                        evidence["fill_price"])
        return _res("UNFILLED_T1_ORDER_EVIDENCE", ev_status_source, evidence["evidence_source"])

    if src is not None and suspended:
        return _res("SUSPENDED_T1_STATUS_CONFIRMED", src)
    if src is not None and restricted:
        return _res("TRADING_RESTRICTED_T1_STATUS_CONFIRMED", src)
    if t1_vol <= 0.0:
        return _res("ZERO_VOLUME_T1", "DAILY_VOLUME")
    if src is None:
        flags.append("NO_TRUSTED_STATUS_SOURCE" if not raw_src else "UNTRUSTED_STATUS_SOURCE")
        if suspended:
            flags.append("SUSPENDED_FLAG_UNTRUSTED")
        return _res("TRADABILITY_UNVERIFIED_T1", raw_src or "NONE")
    if open_at_limit_up:
        # conservative exclusion: an opening limit-up does NOT prove an order went unfilled
        return _res("OPEN_LIMIT_UP_FILL_UNVERIFIED_T1", src)
    if suspended is None or lim is None:
        flags.append("STATUS_INCOMPLETE")
        return _res("TRADABILITY_UNVERIFIED_T1", src)
    return _res("ELIGIBLE_T1_OPEN_STATUS_CHECKED", src)


def build_forward_outcome_labels(
    joined_df: pd.DataFrame,
    *,
    trading_calendar: Optional[Sequence[Any] | pd.Series | pd.DataFrame],
    horizons: Sequence[int] = (1, 3, 5, 10, 20),
    execution_evidence: Optional[pd.DataFrame] = None,
) -> pd.DataFrame:
    """Construct separate T+1 earliest-entry forward outcome table (never mutates T-day feature table, T17).

    Entry convention (RFC Section 6.2):
    - Signal is confirmed at T close; earliest hypothetical entry is T+1 open (`entry_price = open_{T+1}`).
    - For horizon `h`, exit session is calendar index `idx(T) + h` (`h=1` measures `close_{T+1}/open_{T+1}-1`),
      plus `mfe_{h}d` / `mae_{h}d` from the T+1..T+h high/low path.
    - R7: every row carries `t1_fill_status`, `t1_execution_class`, `t1_status_source`,
      `t1_fill_evidence_source`, `t1_risk_flags`, `return_basis`. `fwd_ret/mfe/mae` are HYPOTHETICAL T+1 open
      price returns (factor research) and are NaN only for NO_DATA and status-confirmed non-executable sessions.
      `exec_ret_{h}d` (confirmed-executable statistics) is filled only for `FILLED_T1_ORDER_EVIDENCE` (entry =
      evidence fill price) and `ELIGIBLE_T1_OPEN_STATUS_CHECKED` (entry = T+1 open); never for FILL_UNVERIFIED.
    """
    assert_no_future_columns(joined_df)
    cal = validate_trading_calendar(trading_calendar)
    cal_pos = {d: i for i, d in enumerate(cal)}
    evidence_map = validate_execution_evidence(execution_evidence)
    used_evidence: set[tuple[str, str]] = set()

    required = {"symbol", "trade_date", "open", "high", "low", "close", "volume"}
    missing = required.difference(joined_df.columns)
    if missing:
        raise DataContractError(f"Joined table requires daily OHLCV columns {sorted(missing)} for outcome study")

    work = joined_df.copy()
    work["trade_date"] = normalize_trade_date(work["trade_date"], "trade_date")
    if not work["trade_date"].isin(cal_pos).all():
        outside = sorted(set(work.loc[~work["trade_date"].isin(cal_pos), "trade_date"]))[:3]
        raise DataContractError(f"Joined table contains dates outside trading_calendar: {outside}")
    if work.duplicated(subset=["symbol", "trade_date"]).any():
        raise DataContractError("Duplicate (symbol, trade_date) keys in outcome input")

    def _nan_horizons(rec: dict[str, Any]) -> None:
        for h in horizons:
            rec[f"fwd_ret_{h}d"] = np.nan
            rec[f"mfe_{h}d"] = np.nan
            rec[f"mae_{h}d"] = np.nan
            rec[f"exec_ret_{h}d"] = np.nan

    def _base(rec: dict[str, Any], status: str, status_source: str = "NONE", ev_src: Optional[str] = None,
              flags: str = "NONE") -> None:
        rec["t1_fill_status"] = status
        rec["t1_execution_class"] = T1_STATUS_CLASS[status]
        rec["t1_status_source"] = status_source
        rec["t1_fill_evidence_source"] = ev_src
        rec["t1_risk_flags"] = flags
        rec["return_basis"] = RETURN_BASIS_HYPOTHETICAL
        rec["exec_entry_basis"] = None
        rec["exec_entry_price"] = np.nan

    out_parts: list[pd.DataFrame] = []
    for symbol, grp in work.groupby("symbol", sort=True):
        grp = grp.sort_values("trade_date").reset_index(drop=True)
        by_date = grp.set_index("trade_date")

        rows: list[dict[str, Any]] = []
        for _, row in grp.iterrows():
            t_date = str(row["trade_date"])
            t_idx = cal_pos[t_date]
            rec: dict[str, Any] = {"symbol": symbol, "trade_date": t_date}

            if t_idx + 1 >= len(cal):
                rec["t1_date"] = None
                _base(rec, "PENDING_FUTURE_SESSION")
                _nan_horizons(rec)
                rows.append(rec)
                continue

            t1_date = cal[t_idx + 1]
            rec["t1_date"] = t1_date
            if t1_date not in by_date.index:
                _base(rec, "DATA_MISSING")
                _nan_horizons(rec)
                rows.append(rec)
                continue

            t1_row = by_date.loc[t1_date]
            ev_key = (str(symbol), t1_date)
            ev = evidence_map.get(ev_key)
            if ev is not None:
                used_evidence.add(ev_key)
            res = _t1_tradability(t1_row, ev)
            status = res["fill_status"]
            _base(rec, status, res["status_source"], res["evidence_source"], res["risk_flags"])
            if status in _NO_HYPOTHETICAL_RETURN:
                _nan_horizons(rec)
                rows.append(rec)
                continue

            exec_class = T1_STATUS_CLASS[status]
            if exec_class == "CONFIRMED_FILLED":
                exec_entry = float(res["fill_price"])
                rec["exec_entry_basis"] = "ORDER_EVIDENCE_FILL_PRICE"
            elif exec_class == "STATUS_CHECKED_EXECUTABLE":
                exec_entry = float(t1_row["open"])
                rec["exec_entry_basis"] = "STATUS_CHECKED_T1_OPEN"
            else:
                exec_entry = np.nan
            rec["exec_entry_price"] = exec_entry

            t1_open = float(t1_row["open"])
            for h in horizons:
                end_idx = t_idx + int(h)
                win_dates = cal[t_idx + 1: end_idx + 1] if end_idx < len(cal) else None
                if win_dates is None or not all(d in by_date.index for d in win_dates):
                    rec[f"fwd_ret_{h}d"] = np.nan
                    rec[f"mfe_{h}d"] = np.nan
                    rec[f"mae_{h}d"] = np.nan
                    rec[f"exec_ret_{h}d"] = np.nan
                    continue
                win_slice = by_date.loc[win_dates]
                exit_close = float(win_slice["close"].iloc[-1])
                rec[f"fwd_ret_{h}d"] = exit_close / t1_open - 1.0
                rec[f"mfe_{h}d"] = float(win_slice["high"].max()) / t1_open - 1.0
                rec[f"mae_{h}d"] = float(win_slice["low"].min()) / t1_open - 1.0
                rec[f"exec_ret_{h}d"] = exit_close / exec_entry - 1.0 if pd.notna(exec_entry) else np.nan

            rows.append(rec)
        out_parts.append(pd.DataFrame(rows))

    unmatched = sorted(set(evidence_map) - used_evidence)
    if unmatched:
        raise DataContractError(
            f"Execution evidence does not match any available T+1 entry session: {unmatched[:3]}"
        )
    return pd.concat(out_parts, ignore_index=True)


def run_calendar_block_bootstrap(
    events: pd.DataFrame,
    *,
    trading_calendar: Sequence[Any] | pd.Series | pd.DataFrame,
    block_lengths: Sequence[int] = (5, 10, 20),
    repetitions: int = 500,
    seed: int = 20261013,
    confidence: float = 0.95,
    vlr_dir: Optional[str | Path] = None,
) -> pd.DataFrame:
    """Invoke the read-only `reference/vlr_verify/inference.py::block_bootstrap` without duplicating code (T19)."""
    cal_list = validate_trading_calendar(trading_calendar)
    ref_dir = str(resolve_vlr_verify_dir(vlr_dir))
    if ref_dir not in sys.path:
        sys.path.insert(0, ref_dir)
    import inference  # type: ignore

    return inference.block_bootstrap(
        events,
        trading_calendar=cal_list,
        block_lengths=tuple(int(b) for b in block_lengths),
        repetitions=int(repetitions),
        seed=int(seed),
        confidence=confidence,
    )


def assign_rvol_bucket(rvol: pd.Series, rvol_buckets: Sequence[float]) -> pd.Series:
    """Frozen RVOL bucket index (float, NaN when RVOL missing / outside the frozen edges)."""
    edges = [float(x) for x in rvol_buckets]
    if len(edges) < 2 or any(b <= a for a, b in zip(edges, edges[1:])):
        raise DataContractError(f"rvol_buckets must be strictly increasing with >=2 edges: {edges}")
    return pd.cut(pd.to_numeric(rvol, errors="coerce").astype(float), bins=edges, include_lowest=True,
                  labels=False).astype(float)


def match_controls_same_date_rvol(
    study_df: pd.DataFrame,
    treated_mask: pd.Series,
    *,
    rvol_buckets: Sequence[float] = (0.0, 1.2, 1.5, 2.2, 3.0, 100.0),
    outcome_col: str = "fwd_ret_5d",
    min_events: int = 5,
    seed: int = 20261111,
    board_policy: str = "strict",
) -> dict[str, Any]:
    """Match treated events on `(trade_date, rvol_bucket[, board])` without relaxing criteria silently (T18).

    If no candidate controls exist or matched pairs < `min_events`, returns `status='INCONCLUSIVE'`
    and explicit `unmatched_rate`, never fabricating control observations.

    ``board_policy``:
    - ``strict`` (default): control must share the treated board; a treated row with missing board is unmatched;
      a missing ``board`` column makes the whole comparison ``INCONCLUSIVE`` (``BOARD_COLUMN_MISSING``).
    - ``relax_explicit``: same-board first, otherwise any board on the same date/bucket; every relaxed pair is
      counted in ``n_relaxed_board``.
    - ``ignore``: board is not part of the matching key (``board_constraint='NONE'``).
    Controls are drawn with replacement from the eligible pool using ``seed``.
    """
    if board_policy not in VALID_BOARD_POLICIES:
        raise DataContractError(f"board_policy must be one of {VALID_BOARD_POLICIES}, got {board_policy!r}")
    if "B0_RVRAW" not in study_df.columns:
        raise DataContractError("Matched controls require frozen B0_RVRAW for RVOL bucketing")

    base: dict[str, Any] = {
        "board_policy": board_policy,
        "board_constraint": {"strict": "SAME_BOARD", "relax_explicit": "SAME_BOARD_PREFERRED_RELAXED_COUNTED",
                             "ignore": "NONE"}[board_policy],
        "seed": int(seed),
        "outcome_col": outcome_col,
        "n_relaxed_board": 0,
        "unmatched_reasons": {},
    }

    df = study_df.copy()
    tmask = treated_mask.reindex(df.index).map(lambda v: bool(v) if pd.notna(v) else False).astype(bool)
    df["_rvol_bucket"] = assign_rvol_bucket(df["B0_RVRAW"], rvol_buckets)
    treated = df.loc[tmask & df[outcome_col].notna()].copy()
    pool = df.loc[(~tmask) & df[outcome_col].notna() & df["_rvol_bucket"].notna()].copy()

    n_treated = len(treated)
    empty = {"n_treated": n_treated, "n_matched": 0, "unmatched_rate": np.nan, "mean_treated": np.nan,
             "mean_control": np.nan, "mean_excess": np.nan}
    if n_treated == 0:
        return {**base, **empty, "status": "INCONCLUSIVE", "reason": "NO_TREATED_EVENTS"}
    has_board = "board" in df.columns
    if board_policy == "strict" and not has_board:
        return {**base, **empty, "status": "INCONCLUSIVE", "reason": "BOARD_COLUMN_MISSING",
                "unmatched_rate": 1.0}

    rng = np.random.default_rng(seed)
    matched_diffs: list[float] = []
    matched_ctrl_vals: list[float] = []
    matched_trt_vals: list[float] = []
    reasons: dict[str, int] = {}
    n_relaxed = 0

    for _, trow in treated.iterrows():
        if pd.isna(trow["_rvol_bucket"]):
            reasons["RVOL_MISSING"] = reasons.get("RVOL_MISSING", 0) + 1
            continue
        cands = pool.loc[
            (pool["trade_date"] == trow["trade_date"])
            & (pool["_rvol_bucket"] == trow["_rvol_bucket"])
            & (pool["symbol"] != trow["symbol"])
        ]
        if board_policy in ("strict", "relax_explicit") and has_board:
            t_board = trow.get("board")
            if pd.isna(t_board):
                if board_policy == "strict":
                    reasons["TREATED_BOARD_MISSING"] = reasons.get("TREATED_BOARD_MISSING", 0) + 1
                    continue
                board_cands = cands.iloc[0:0]
            else:
                board_cands = cands.loc[cands["board"] == t_board]
            if board_cands.empty and board_policy == "relax_explicit" and not cands.empty:
                n_relaxed += 1  # explicit, counted relaxation
            else:
                cands = board_cands
        if cands.empty:
            reasons["NO_CANDIDATE"] = reasons.get("NO_CANDIDATE", 0) + 1
            continue
        chosen = cands.iloc[int(rng.integers(0, len(cands)))]
        t_val = float(trow[outcome_col])
        c_val = float(chosen[outcome_col])
        matched_trt_vals.append(t_val)
        matched_ctrl_vals.append(c_val)
        matched_diffs.append(t_val - c_val)

    n_matched = len(matched_diffs)
    unmatched = n_treated - n_matched
    unmatched_rate = float(unmatched) / float(n_treated)
    status = "OK" if n_matched >= min_events else "INCONCLUSIVE"
    reason = "SUFFICIENT_MATCHED_PAIRS" if status == "OK" else "INSUFFICIENT_MATCHED_CONTROLS"

    return {
        **base,
        "status": status,
        "reason": reason,
        "n_treated": n_treated,
        "n_matched": n_matched,
        "n_relaxed_board": n_relaxed,
        "unmatched_reasons": reasons,
        "unmatched_rate": unmatched_rate,
        "mean_treated": float(np.mean(matched_trt_vals)) if n_matched > 0 else np.nan,
        "mean_control": float(np.mean(matched_ctrl_vals)) if n_matched > 0 else np.nan,
        "mean_excess": float(np.mean(matched_diffs)) if n_matched > 0 else np.nan,
    }


def permute_within_buckets(values: np.ndarray, buckets: np.ndarray, rng: np.random.Generator) -> np.ndarray:
    """Permute ``values`` independently inside each bucket label (bucket sizes and value multisets preserved)."""
    values = np.asarray(values, dtype=float)
    buckets = np.asarray(buckets)
    out = values.copy()
    for b in np.unique(buckets):
        idx = np.flatnonzero(buckets == b)
        if len(idx) > 1:
            out[idx] = values[rng.permutation(idx)]
    return out


def permutation_negative_control(
    study_df: pd.DataFrame,
    base_event_col: str,
    *,
    mbv_share_cut: float = 0.15,
    outcome_col: str = "fwd_ret_5d",
    n_permutations: int = 1000,
    min_events: int = 5,
    seed: int = 20261111,
    rvol_buckets: Sequence[float] = (0.0, 1.2, 1.5, 2.2, 3.0, 100.0),
) -> dict[str, Any]:
    """Group E negative control: permute MBV features within RVOL buckets to check whether apparent
    MBV stratification is merely a noisy proxy for daily RVOL.

    R6: permutation happens ONLY inside frozen ``B0_RVRAW`` buckets (``rvol_buckets``), preserving bucket sizes.
    Events with missing RVOL are excluded and counted. A bucket is *permutable* when it holds >=2 events with
    both high (``burst_share >= mbv_share_cut``) and low MBV members; without any permutable bucket the
    control is ``INCONCLUSIVE``. Reports two-sided p-value ``(1 + #|perm| >= |obs|) / (1 + n_valid)``.
    """
    base: dict[str, Any] = {
        "method": "WITHIN_RVOL_BUCKET_PERMUTATION",
        "seed": int(seed),
        "n_permutations_requested": int(n_permutations),
        "n_permutations_valid": 0,
        "rvol_buckets": [float(x) for x in rvol_buckets],
        "bucket_counts": {},
        "n_rvol_missing": 0,
        "observed_spread": np.nan,
        "permuted_mean_spread": np.nan,
        "p_value_two_sided": np.nan,
    }
    if n_permutations < 1:
        raise DataContractError("n_permutations must be >= 1")
    if base_event_col not in study_df.columns:
        return {**base, "status": "INCONCLUSIVE", "reason": "BASE_EVENT_COLUMN_MISSING", "n_events": 0}
    if "B0_RVRAW" not in study_df.columns:
        return {**base, "status": "INCONCLUSIVE", "reason": "RVOL_UNAVAILABLE", "n_events": 0}

    sub = study_df.loc[
        _bool_series(study_df, base_event_col)
        & (study_df["feature_status"] == "OK")
        & study_df[outcome_col].notna()
    ].copy()
    sub["_rvol_bucket"] = assign_rvol_bucket(sub["B0_RVRAW"], rvol_buckets)
    n_rvol_missing = int(sub["_rvol_bucket"].isna().sum())
    sub = sub.loc[sub["_rvol_bucket"].notna()]
    base["n_rvol_missing"] = n_rvol_missing
    base["bucket_counts"] = {int(k): int(v) for k, v in sub["_rvol_bucket"].value_counts().sort_index().items()}

    if len(sub) < min_events:
        return {**base, "status": "INCONCLUSIVE", "reason": "INSUFFICIENT_BASE_EVENTS_FOR_PERMUTATION",
                "n_events": len(sub)}

    hi_mask = sub["burst_share"] >= mbv_share_cut
    lo_mask = ~hi_mask
    if hi_mask.sum() == 0 or lo_mask.sum() == 0:
        return {**base, "status": "INCONCLUSIVE", "reason": "DEGENERATE_SPLIT", "n_events": len(sub)}

    buckets = sub["_rvol_bucket"].to_numpy()
    shares = sub["burst_share"].to_numpy(dtype=float)
    outcomes = sub[outcome_col].to_numpy(dtype=float)
    permutable = [
        b for b in np.unique(buckets)
        if (buckets == b).sum() >= 2 and 0 < (shares[buckets == b] >= mbv_share_cut).sum() < (buckets == b).sum()
    ]
    obs_spread = float(outcomes[hi_mask.to_numpy()].mean() - outcomes[lo_mask.to_numpy()].mean())
    base["observed_spread"] = obs_spread
    base["n_permutable_buckets"] = len(permutable)
    if not permutable:
        return {**base, "status": "INCONCLUSIVE", "reason": "NO_PERMUTABLE_RVOL_BUCKET", "n_events": len(sub)}

    rng = np.random.default_rng(seed)
    perm_spreads: list[float] = []
    for _ in range(int(n_permutations)):
        perm = permute_within_buckets(shares, buckets, rng)
        p_hi = perm >= mbv_share_cut
        if p_hi.sum() > 0 and (~p_hi).sum() > 0:
            perm_spreads.append(float(outcomes[p_hi].mean() - outcomes[~p_hi].mean()))

    n_valid = len(perm_spreads)
    if n_valid == 0:
        return {**base, "status": "INCONCLUSIVE", "reason": "NO_VALID_PERMUTATION", "n_events": len(sub)}
    arr = np.asarray(perm_spreads)
    p_val = float((1 + np.sum(np.abs(arr) >= abs(obs_spread) - 1e-15)) / (1 + n_valid))
    return {
        **base,
        "status": "COMPLETED",
        "reason": "COMPLETED_WITHIN_BUCKET",
        "n_events": len(sub),
        "n_permutations_valid": n_valid,
        "permuted_mean_spread": float(arr.mean()),
        "p_value_two_sided": p_val,
    }


def run_event_study(
    joined_df: pd.DataFrame,
    *,
    trading_calendar: Optional[Sequence[Any] | pd.Series | pd.DataFrame],
    study_mode: str = "SYNTHETIC_DEMO",
    horizons: Sequence[int] = (1, 3, 5, 10, 20),
    min_events_per_group: int = 5,
    mbv_share_cut: float = 0.15,
    mbv_dominance_cut: float = 0.25,
    mbv_abs_dom_weak_cut: float = 0.25,
    rvol_buckets: Sequence[float] = (0.0, 1.2, 1.5, 2.2, 3.0, 100.0),
    bootstrap_blocks: Sequence[int] = (5, 10, 20),
    bootstrap_repetitions: int = 500,
    bootstrap_seed: int = 20261013,
    confidence: float = 0.95,
    vlr_dir: Optional[str | Path] = None,
    board_policy: str = "strict",
    matching_seed: int = 20261111,
    permutation_n: int = 1000,
    permutation_seed: int = 20261111,
    calendar_provenance: Optional[dict[str, Any]] = None,
    preregistration: Optional[dict[str, Any]] = None,
    execution_evidence: Optional[pd.DataFrame] = None,
) -> dict[str, Any]:
    """Execute the 5-arm pre-registered research evaluation (Groups A–E) with strict status reporting.

    - Enforces `assert_no_future_columns(joined_df)` (T17) and `validate_trading_calendar` (T16).
    - Labels all outputs with `study_mode` (`SYNTHETIC_DEMO` unless verified real data is declared, T20).
    - Reports sample attrition (`feature_status` counts, `t1_fill_status` counts), group summaries,
      matched control diagnostics (Group D), permutation negative control (Group E), and calendar
      block bootstrap where event coverage permits.
    - R6: explicit ``conclusion`` (never an alpha claim for synthetic / unverified data) and ``gates``.
    - R7: ``resolve_study_context`` (formal modes: verified exchange calendar + provenance; OOS: pre-registration),
      MBV feature ``calendar_sha256`` must equal the study calendar, OOS trade dates must lie in the registered
      window, and confirmed-executable return statistics (``exec_*``) exclude FILL_UNVERIFIED rows.
    """
    if study_mode not in VALID_STUDY_LABELS:
        raise DataContractError(f"Invalid study_mode '{study_mode}'; must be one of {VALID_STUDY_LABELS}")
    if board_policy not in VALID_BOARD_POLICIES:
        raise DataContractError(f"board_policy must be one of {VALID_BOARD_POLICIES}, got {board_policy!r}")

    assert_no_future_columns(joined_df)
    cal_list = validate_trading_calendar(trading_calendar)
    if "feature_status" not in joined_df.columns:
        raise DataContractError("Joined table lacks required 'feature_status' column")
    ctx = resolve_study_context(study_mode, cal_list, calendar_provenance=calendar_provenance,
                                preregistration=preregistration, require_calendar=True)
    assert_feature_calendar_consistent(ctx, joined_df)
    assert_dates_in_preregistered_window(ctx, joined_df["trade_date"], allow_warmup=False)

    outcomes = build_forward_outcome_labels(
        joined_df, trading_calendar=cal_list, horizons=horizons, execution_evidence=execution_evidence
    )
    study_df = pd.merge(
        joined_df.assign(trade_date=normalize_trade_date(joined_df["trade_date"], "trade_date")),
        outcomes, on=["symbol", "trade_date"], how="left", validate="one_to_one",
    )

    mbv_ok = study_df["feature_status"] == "OK"
    b0_eu = _bool_series(study_df, "B0_EU")
    b0_abu = _bool_series(study_df, "B0_ABU")
    b0_vu = _bool_series(study_df, "B0_VU")
    share = study_df["burst_share"] if "burst_share" in study_df.columns else pd.Series(np.nan, index=study_df.index)
    dom = study_df["burst_dominance"] if "burst_dominance" in study_df.columns else pd.Series(np.nan, index=study_df.index)
    cnt = study_df["burst_count"] if "burst_count" in study_df.columns else pd.Series(np.nan, index=study_df.index)
    high_bull = (share >= mbv_share_cut) & (dom >= mbv_dominance_cut)

    groups: dict[str, pd.Series] = {
        "A_VLR_EU_ONLY": b0_eu,
        "A_VLR_ABU_ONLY": b0_abu,
        "A_VLR_VU_ONLY": b0_vu,
        "B_MBV_BULL_BURST_ONLY": mbv_ok & high_bull,
        "C_H1_EU_HIGH_BULL_MBV": b0_eu & mbv_ok & high_bull,
        "C_H1_EU_LOW_OR_WEAK_MBV": b0_eu & mbv_ok & ~high_bull,
        "C_H2_ABU_OFFSETTING_MBV": b0_abu & mbv_ok & (share >= mbv_share_cut) & (dom.abs() <= mbv_abs_dom_weak_cut),
        "C_H3_VU_NO_BURST": b0_vu & mbv_ok & (cnt == 0),
        "C_H3_VU_LOCAL_BURST": b0_vu & mbv_ok & (cnt >= 1),
    }

    summary_rows: list[dict[str, Any]] = []
    for g_name, mask in groups.items():
        sub = study_df.loc[mask]
        n_raw = int(len(sub))
        for h in horizons:
            ret_col = f"fwd_ret_{h}d"
            mfe_col = f"mfe_{h}d"
            mae_col = f"mae_{h}d"
            valid_sub = sub.loc[sub[ret_col].notna()] if ret_col in sub.columns else pd.DataFrame()
            n_eff = int(len(valid_sub))
            status = "OK" if n_eff >= min_events_per_group else "INCONCLUSIVE"
            if n_eff > 0:
                vals = valid_sub[ret_col].to_numpy(dtype=float)
                mean_ret = float(np.mean(vals))
                med_ret = float(np.median(vals))
                win_rate = float(np.mean(vals > 0.0))
                mean_mfe = float(valid_sub[mfe_col].mean())
                mean_mae = float(valid_sub[mae_col].mean())
            else:
                mean_ret = med_ret = win_rate = mean_mfe = mean_mae = np.nan

            exec_col = f"exec_ret_{h}d"
            exec_vals = sub[exec_col].dropna().to_numpy(dtype=float) if exec_col in sub.columns else np.array([])
            n_unverified = int((sub["t1_execution_class"] == "FILL_UNVERIFIED").sum()) \
                if "t1_execution_class" in sub.columns else 0

            summary_rows.append({
                "study_mode": study_mode,
                "group": g_name,
                "horizon_days": int(h),
                "raw_events": n_raw,
                "return_basis": RETURN_BASIS_HYPOTHETICAL,
                "effective_events": n_eff,
                "dropped_missing_return": n_raw - n_eff,
                "mean_return": mean_ret,
                "median_return": med_ret,
                "win_rate": win_rate,
                "mean_mfe": mean_mfe,
                "mean_mae": mean_mae,
                "fill_unverified_events": n_unverified,
                "exec_effective_events": int(len(exec_vals)),
                "exec_mean_return": float(np.mean(exec_vals)) if len(exec_vals) else np.nan,
                "group_status": status,
            })

    summary_df = pd.DataFrame(summary_rows)

    # Group D: Matched controls for H1 primary endpoint (5d return) and H2 primary endpoint (5d MAE)
    primary_h = 5 if 5 in horizons else int(horizons[0])
    d_h1 = match_controls_same_date_rvol(
        study_df,
        groups["C_H1_EU_HIGH_BULL_MBV"],
        rvol_buckets=rvol_buckets,
        outcome_col=f"fwd_ret_{primary_h}d",
        min_events=min_events_per_group,
        seed=matching_seed,
        board_policy=board_policy,
    )
    d_h2 = match_controls_same_date_rvol(
        study_df,
        groups["C_H2_ABU_OFFSETTING_MBV"],
        rvol_buckets=rvol_buckets,
        outcome_col=f"mae_{primary_h}d",
        min_events=min_events_per_group,
        seed=matching_seed,
        board_policy=board_policy,
    )

    # Group E: within-RVOL-bucket permutation negative control inside B0_EU (no silent fallback base column)
    e_perm = permutation_negative_control(
        study_df,
        "B0_EU",
        mbv_share_cut=mbv_share_cut,
        outcome_col=f"fwd_ret_{primary_h}d",
        n_permutations=permutation_n,
        min_events=min_events_per_group,
        seed=permutation_seed,
        rvol_buckets=rvol_buckets,
    )

    # Calendar-block bootstrap on primary MBV events; evaluation calendar = sessions spanned by minute coverage
    ret_col = f"fwd_ret_{primary_h}d"
    b_mask = groups["B_MBV_BULL_BURST_ONLY"]
    boot_target = study_df.loc[b_mask & study_df[ret_col].notna(), ["trade_date", ret_col]].rename(
        columns={"trade_date": "date", ret_col: "return"}
    )
    covered = study_df.loc[study_df["feature_status"] != "MISSING_MINUTE_DATA", "trade_date"]
    if covered.empty:
        eval_cal: list[str] = []
    else:
        eval_cal = [d for d in cal_list if covered.min() <= d <= covered.max()]
    requested_blocks = [int(b) for b in bootstrap_blocks]
    valid_blocks = [b for b in requested_blocks if 2 * b <= len(eval_cal)]
    bootstrap_info: dict[str, Any] = {
        "target_group": "B_MBV_BULL_BURST_ONLY",
        "outcome_col": ret_col,
        "seed": int(bootstrap_seed),
        "repetitions": int(bootstrap_repetitions),
        "confidence": float(confidence),
        "evaluation_sessions": len(eval_cal),
        "evaluation_window": [eval_cal[0], eval_cal[-1]] if eval_cal else None,
        "block_lengths_requested": requested_blocks,
        "block_lengths_used": valid_blocks,
        "block_lengths_dropped_too_long": [b for b in requested_blocks if b not in valid_blocks],
        "raw_events": int(b_mask.sum()),
        "events_used": int(len(boot_target)),
        "events_dropped_missing_return": int(b_mask.sum() - len(boot_target)),
    }

    bootstrap_status = "OK"
    bootstrap_detail = ""
    bootstrap_df = pd.DataFrame()
    if boot_target.empty or not valid_blocks:
        bootstrap_status = "INCONCLUSIVE"
        bootstrap_detail = "Insufficient event coverage or short evaluation calendar for block bootstrap"
    else:
        try:
            bootstrap_df = run_calendar_block_bootstrap(
                boot_target,
                trading_calendar=eval_cal,
                block_lengths=valid_blocks,
                repetitions=bootstrap_repetitions,
                seed=bootstrap_seed,
                confidence=confidence,
                vlr_dir=vlr_dir,
            )
        except ValueError as exc:
            bootstrap_status = "INCONCLUSIVE"
            bootstrap_detail = str(exc)

    feature_status_counts = {str(k): int(v) for k, v in study_df["feature_status"].value_counts(dropna=False).items()}
    fill_status_counts = {str(k): int(v) for k, v in study_df["t1_fill_status"].value_counts(dropna=False).items()}
    exec_class_counts = {str(k): int(v) for k, v in study_df["t1_execution_class"].value_counts(dropna=False).items()}

    if study_mode == "SYNTHETIC_DEMO":
        conclusion = ("NO_RESEARCH_CONCLUSION: SYNTHETIC_DEMO output only exercises the code path; "
                      "it is not evidence of MBV incremental value or alpha.")
        interpretation = "NOT_EVIDENCE_SYNTHETIC"
    else:
        conclusion = ("PROVISIONAL_RESEARCH_ONLY: G1/G2/G3 gates are not passed; results must not be used as "
                      "alpha or trading evidence.")
        interpretation = "PROVISIONAL_UNVERIFIED"
    e_perm = {**e_perm, "interpretation": interpretation}

    return {
        "study_mode": study_mode,
        "research_grade": ctx.research_grade,
        "study_context": ctx.describe(),
        "vlr_parity_status": "TDX_PARITY_NOT_VERIFIED",
        "conclusion": conclusion,
        "gates": dict(GATE_STATUS),
        "calendar_sessions": len(cal_list),
        "total_panel_rows": len(study_df),
        "feature_status_counts": feature_status_counts,
        "t1_fill_status_counts": fill_status_counts,
        "t1_execution_class_counts": exec_class_counts,
        "group_summary": summary_df,
        "matched_control_h1": d_h1,
        "matched_control_h2": d_h2,
        "permutation_control_e": e_perm,
        "bootstrap_status": bootstrap_status,
        "bootstrap_detail": bootstrap_detail,
        "bootstrap_info": bootstrap_info,
        "bootstrap_table": bootstrap_df,
        "outcomes_table": outcomes,
    }


def format_study_markdown_report(study_result: dict[str, Any]) -> str:
    """Render reproducible Markdown report with prominent SYNTHETIC_DEMO / gate disclaimers (T20)."""
    mode = study_result["study_mode"]
    banner = (
        f"> **STUDY LABEL: `{mode}`** | Research Grade: `{study_result['research_grade']}` | "
        f"VLR Parity: `{study_result['vlr_parity_status']}`\n"
        "> **WARNING**: Intraday OHLCV body efficiency is a structural proxy ONLY — NOT order-flow or "
        "active buy/sell volume. Do NOT interpret synthetic or unverified outputs as alpha or live trading signals.\n"
        f"> **CONCLUSION**: {study_result.get('conclusion', '')}\n"
    )
    gates = study_result.get("gates", {})
    lines = [
        f"# MBV V0.1 Event Study Report (`{mode}`)",
        "",
        banner,
        "## 0. Gates",
        *[f"- `{k}`: `{v}`" for k, v in gates.items()],
        "",
        "## 0b. Study Context (calendar / pre-registration)",
        f"- **Study Context**: `{study_result.get('study_context', {})}`",
        "",
        "## 1. Sample Coverage & Attrition",
        f"- **Evaluation Calendar Sessions**: `{study_result['calendar_sessions']}`",
        f"- **Total Daily Panel Rows**: `{study_result['total_panel_rows']}`",
        f"- **MBV `feature_status` Counts**: `{study_result['feature_status_counts']}`",
        f"- **T+1 `fill_status` Counts**: `{study_result['t1_fill_status_counts']}`",
        f"- **T+1 `execution_class` Counts**: `{study_result.get('t1_execution_class_counts', {})}`",
        "- **Return basis**: `fwd_ret_*` / `mean_return` are HYPOTHETICAL T+1 open-price returns (factor research) "
        "and are NOT fill returns. `exec_*` statistics include only CONFIRMED_FILLED (order evidence) and "
        "STATUS_CHECKED_EXECUTABLE rows; FILL_UNVERIFIED rows (incl. OPEN_LIMIT_UP_FILL_UNVERIFIED_T1) are excluded.",
        "",
        "## 2. Matched & Permutation Controls (Groups D & E)",
        f"- **H1 Matched Control (Same-Date + RVOL Bucket + board policy)**: `{study_result['matched_control_h1']}`",
        f"- **H2 Matched Control (Same-Date + RVOL Bucket + board policy)**: `{study_result['matched_control_h2']}`",
        f"- **Group E Within-RVOL-Bucket Permutation Negative Control**: `{study_result['permutation_control_e']}`",
        "",
        "## 3. Calendar-Block Bootstrap (`reference/vlr_verify/inference.py`)",
        f"- **Bootstrap Status**: `{study_result['bootstrap_status']}` {study_result['bootstrap_detail']}",
        f"- **Bootstrap Settings / Attrition**: `{study_result.get('bootstrap_info', {})}`",
    ]
    bdf: pd.DataFrame = study_result["bootstrap_table"]
    if not bdf.empty:
        lines.append("")
        lines.append("```text")
        lines.append(bdf.to_string(index=False))
        lines.append("```")

    lines.extend([
        "",
        "## 4. Group × Horizon Summary",
        "",
        "```text",
        study_result["group_summary"].to_string(index=False),
        "```",
        "",
    ])
    return "\n".join(lines)
