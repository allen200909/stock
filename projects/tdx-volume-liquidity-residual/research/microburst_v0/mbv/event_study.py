"""Event study, matched/permutation controls, T+1 forward outcomes, and block bootstrap wrapper."""
from __future__ import annotations

from pathlib import Path
import sys
from typing import Any, Optional, Sequence

import numpy as np
import pandas as pd

from mbv.join import resolve_vlr_verify_dir
from mbv.schema import DataContractError, assert_no_future_columns, normalize_trade_date


VALID_STUDY_LABELS = ("SYNTHETIC_DEMO", "EXPLORATORY_REAL_DATA", "CONFIRMATORY_OOS")


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
    norm = normalize_trade_date(raw, "trading_calendar")
    if norm.duplicated().any():
        raise DataContractError("trading_calendar must contain unique trading dates")
    if not norm.is_monotonic_increasing:
        raise DataContractError("trading_calendar must be sorted chronologically")
    return norm.tolist()


def build_forward_outcome_labels(
    joined_df: pd.DataFrame,
    *,
    trading_calendar: Optional[Sequence[Any] | pd.Series | pd.DataFrame],
    horizons: Sequence[int] = (1, 3, 5, 10, 20),
) -> pd.DataFrame:
    """Construct separate T+1 earliest-entry forward outcome table (never mutates T-day feature table, T17).

    Entry convention (RFC Section 6.2):
    - Signal is confirmed at T close; earliest hypothetical entry is T+1 open (`entry_price = open_{T+1}`).
    - If T+1 is absent, suspended (`volume == 0`), or locked (`high == low` on T+1), `fill_status`
      is recorded (`DATA_MISSING`, `UNFILLED_SUSPENDED`, `UNFILLED_LOCKED_T1`) and returns are `NaN`.
    - For horizon `h` in `horizons`, exit session is calendar index `idx(T) + h` (so `h=1` measures
      `close_{T+1} / open_{T+1} - 1`, `h=5` measures `close_{T+5} / open_{T+1} - 1`, etc.), plus
      `mfe_{h}d` (`max(high_{T+1..T+h}) / open_{T+1} - 1`) and `mae_{h}d` (`min(low_{T+1..T+h}) / open_{T+1} - 1`).
    """
    assert_no_future_columns(joined_df)
    cal = validate_trading_calendar(trading_calendar)
    cal_pos = {d: i for i, d in enumerate(cal)}

    required = {"symbol", "trade_date", "open", "high", "low", "close", "volume"}
    missing = required.difference(joined_df.columns)
    if missing:
        raise DataContractError(f"Joined table requires daily OHLCV columns {sorted(missing)} for outcome study")

    work = joined_df.copy()
    work["trade_date"] = normalize_trade_date(work["trade_date"], "trade_date")
    if not work["trade_date"].isin(cal_pos).all():
        outside = sorted(set(work.loc[~work["trade_date"].isin(cal_pos), "trade_date"]))[:3]
        raise DataContractError(f"Joined table contains dates outside trading_calendar: {outside}")

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
                rec["t1_fill_status"] = "PENDING_FUTURE_SESSION"
                for h in horizons:
                    rec[f"fwd_ret_{h}d"] = np.nan
                    rec[f"mfe_{h}d"] = np.nan
                    rec[f"mae_{h}d"] = np.nan
                rows.append(rec)
                continue

            t1_date = cal[t_idx + 1]
            if t1_date not in by_date.index:
                rec["t1_fill_status"] = "DATA_MISSING"
                for h in horizons:
                    rec[f"fwd_ret_{h}d"] = np.nan
                    rec[f"mfe_{h}d"] = np.nan
                    rec[f"mae_{h}d"] = np.nan
                rows.append(rec)
                continue

            t1_row = by_date.loc[t1_date]
            t1_open = float(t1_row["open"])
            t1_high = float(t1_row["high"])
            t1_low = float(t1_row["low"])
            t1_vol = float(t1_row["volume"])

            if t1_vol <= 0.0:
                rec["t1_fill_status"] = "UNFILLED_SUSPENDED_T1"
                for h in horizons:
                    rec[f"fwd_ret_{h}d"] = np.nan
                    rec[f"mfe_{h}d"] = np.nan
                    rec[f"mae_{h}d"] = np.nan
                rows.append(rec)
                continue

            if t1_high == t1_low:
                rec["t1_fill_status"] = "UNFILLED_LOCKED_T1"
                for h in horizons:
                    rec[f"fwd_ret_{h}d"] = np.nan
                    rec[f"mfe_{h}d"] = np.nan
                    rec[f"mae_{h}d"] = np.nan
                rows.append(rec)
                continue

            rec["t1_fill_status"] = "ELIGIBLE_FOR_FILL_CHECK"
            for h in horizons:
                end_idx = t_idx + int(h)
                if end_idx >= len(cal):
                    rec[f"fwd_ret_{h}d"] = np.nan
                    rec[f"mfe_{h}d"] = np.nan
                    rec[f"mae_{h}d"] = np.nan
                    continue
                win_dates = cal[t_idx + 1 : end_idx + 1]
                if not all(d in by_date.index for d in win_dates):
                    rec[f"fwd_ret_{h}d"] = np.nan
                    rec[f"mfe_{h}d"] = np.nan
                    rec[f"mae_{h}d"] = np.nan
                    continue
                win_slice = by_date.loc[win_dates]
                exit_close = float(win_slice["close"].iloc[-1])
                max_high = float(win_slice["high"].max())
                min_low = float(win_slice["low"].min())
                rec[f"fwd_ret_{h}d"] = exit_close / t1_open - 1.0
                rec[f"mfe_{h}d"] = max_high / t1_open - 1.0
                rec[f"mae_{h}d"] = min_low / t1_open - 1.0

            rows.append(rec)
        out_parts.append(pd.DataFrame(rows))

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
        block_lengths=tuple(block_lengths),
        repetitions=repetitions,
        seed=seed,
        confidence=confidence,
    )


def match_controls_same_date_rvol(
    study_df: pd.DataFrame,
    treated_mask: pd.Series,
    *,
    rvol_buckets: Sequence[float] = (0.0, 1.2, 1.5, 2.2, 3.0, 100.0),
    outcome_col: str = "fwd_ret_5d",
    min_events: int = 5,
    seed: int = 20261111,
) -> dict[str, Any]:
    """Match treated events on `(trade_date, rvol_bucket[, board])` without relaxing criteria silently (T18).

    If no candidate controls exist or matched pairs < `min_events`, returns `status='INCONCLUSIVE'`
    and explicit `unmatched_rate`, never fabricating control observations.
    """
    df = study_df.copy()
    df["_rvol_bucket"] = pd.cut(
        df["B0_RVRAW"].astype(float),
        bins=list(rvol_buckets),
        include_lowest=True,
        labels=False,
    )
    treated = df.loc[treated_mask & df[outcome_col].notna()].copy()
    pool = df.loc[(~treated_mask) & df[outcome_col].notna()].copy()

    n_treated = len(treated)
    if n_treated == 0:
        return {
            "status": "INCONCLUSIVE",
            "reason": "NO_TREATED_EVENTS",
            "n_treated": 0,
            "n_matched": 0,
            "unmatched_rate": np.nan,
            "mean_treated": np.nan,
            "mean_control": np.nan,
            "mean_excess": np.nan,
        }

    rng = np.random.default_rng(seed)
    matched_diffs: list[float] = []
    matched_ctrl_vals: list[float] = []
    matched_trt_vals: list[float] = []
    unmatched = 0

    has_board = "board" in df.columns
    for _, trow in treated.iterrows():
        cands = pool.loc[
            (pool["trade_date"] == trow["trade_date"])
            & (pool["_rvol_bucket"] == trow["_rvol_bucket"])
            & (pool["symbol"] != trow["symbol"])
        ]
        if has_board and pd.notna(trow.get("board")):
            board_cands = cands.loc[cands["board"] == trow["board"]]
            if not board_cands.empty:
                cands = board_cands
        if cands.empty:
            unmatched += 1
            continue
        chosen = cands.iloc[int(rng.integers(0, len(cands)))]
        t_val = float(trow[outcome_col])
        c_val = float(chosen[outcome_col])
        matched_trt_vals.append(t_val)
        matched_ctrl_vals.append(c_val)
        matched_diffs.append(t_val - c_val)

    n_matched = len(matched_diffs)
    unmatched_rate = float(unmatched) / float(n_treated)
    status = "OK" if n_matched >= min_events else "INCONCLUSIVE"
    reason = "SUFFICIENT_MATCHED_PAIRS" if status == "OK" else "INSUFFICIENT_MATCHED_CONTROLS"

    return {
        "status": status,
        "reason": reason,
        "n_treated": n_treated,
        "n_matched": n_matched,
        "unmatched_rate": unmatched_rate,
        "mean_treated": float(np.mean(matched_trt_vals)) if n_matched > 0 else np.nan,
        "mean_control": float(np.mean(matched_ctrl_vals)) if n_matched > 0 else np.nan,
        "mean_excess": float(np.mean(matched_diffs)) if n_matched > 0 else np.nan,
    }


def permutation_negative_control(
    study_df: pd.DataFrame,
    base_event_col: str,
    *,
    mbv_share_cut: float = 0.15,
    outcome_col: str = "fwd_ret_5d",
    n_permutations: int = 100,
    min_events: int = 5,
    seed: int = 20261111,
) -> dict[str, Any]:
    """Group E negative control: permute MBV features within RVOL buckets to check whether apparent
    MBV stratification is merely a noisy proxy for daily RVOL."""
    sub = study_df.loc[
        study_df[base_event_col].fillna(False).astype(bool)
        & (study_df["feature_status"] == "OK")
        & study_df[outcome_col].notna()
    ].copy()
    if len(sub) < min_events:
        return {
            "status": "INCONCLUSIVE",
            "reason": "INSUFFICIENT_BASE_EVENTS_FOR_PERMUTATION",
            "n_events": len(sub),
            "observed_spread": np.nan,
            "permuted_mean_spread": np.nan,
        }

    hi_mask = sub["burst_share"] >= mbv_share_cut
    lo_mask = ~hi_mask
    if hi_mask.sum() == 0 or lo_mask.sum() == 0:
        return {
            "status": "INCONCLUSIVE",
            "reason": "DEGENERATE_SPLIT",
            "n_events": len(sub),
            "observed_spread": np.nan,
            "permuted_mean_spread": np.nan,
        }

    obs_spread = float(sub.loc[hi_mask, outcome_col].mean() - sub.loc[lo_mask, outcome_col].mean())
    rng = np.random.default_rng(seed)
    perm_spreads: list[float] = []
    shares = sub["burst_share"].to_numpy(dtype=float)
    outcomes = sub[outcome_col].to_numpy(dtype=float)

    for _ in range(n_permutations):
        perm = rng.permutation(shares)
        p_hi = perm >= mbv_share_cut
        if p_hi.sum() > 0 and (~p_hi).sum() > 0:
            perm_spreads.append(float(outcomes[p_hi].mean() - outcomes[~p_hi].mean()))

    return {
        "status": "OK" if len(perm_spreads) > 0 else "INCONCLUSIVE",
        "reason": "COMPLETED",
        "n_events": len(sub),
        "observed_spread": obs_spread,
        "permuted_mean_spread": float(np.mean(perm_spreads)) if perm_spreads else np.nan,
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
) -> dict[str, Any]:
    """Execute the 5-arm pre-registered research evaluation (Groups A–E) with strict status reporting.

    - Enforces `assert_no_future_columns(joined_df)` (T17) and `validate_trading_calendar` (T16).
    - Labels all outputs with `study_mode` (`SYNTHETIC_DEMO` unless verified real data is declared, T20).
    - Reports sample attrition (`feature_status` counts, `t1_fill_status` counts), group summaries,
      matched control diagnostics (Group D), permutation negative control (Group E), and calendar
      block bootstrap where event coverage permits.
    """
    if study_mode not in VALID_STUDY_LABELS:
        raise DataContractError(f"Invalid study_mode '{study_mode}'; must be one of {VALID_STUDY_LABELS}")

    assert_no_future_columns(joined_df)
    cal_list = validate_trading_calendar(trading_calendar)

    outcomes = build_forward_outcome_labels(
        joined_df, trading_calendar=cal_list, horizons=horizons
    )
    study_df = pd.merge(joined_df, outcomes, on=["symbol", "trade_date"], how="left", validate="one_to_one")

    mbv_ok = study_df["feature_status"] == "OK"
    b0_eu = study_df.get("B0_EU", pd.Series(False, index=study_df.index)).fillna(False).astype(bool)
    b0_abu = study_df.get("B0_ABU", pd.Series(False, index=study_df.index)).fillna(False).astype(bool)
    b0_vu = study_df.get("B0_VU", pd.Series(False, index=study_df.index)).fillna(False).astype(bool)

    groups: dict[str, pd.Series] = {
        "A_VLR_EU_ONLY": b0_eu,
        "A_VLR_ABU_ONLY": b0_abu,
        "A_VLR_VU_ONLY": b0_vu,
        "B_MBV_BULL_BURST_ONLY": mbv_ok
        & (study_df["burst_share"] >= mbv_share_cut)
        & (study_df["burst_dominance"] >= mbv_dominance_cut),
        "C_H1_EU_HIGH_BULL_MBV": b0_eu
        & mbv_ok
        & (study_df["burst_share"] >= mbv_share_cut)
        & (study_df["burst_dominance"] >= mbv_dominance_cut),
        "C_H1_EU_LOW_OR_WEAK_MBV": b0_eu
        & mbv_ok
        & ~((study_df["burst_share"] >= mbv_share_cut) & (study_df["burst_dominance"] >= mbv_dominance_cut)),
        "C_H2_ABU_OFFSETTING_MBV": b0_abu
        & mbv_ok
        & (study_df["burst_share"] >= mbv_share_cut)
        & (study_df["burst_dominance"].abs() <= mbv_abs_dom_weak_cut),
        "C_H3_VU_NO_BURST": b0_vu & mbv_ok & (study_df["burst_count"] == 0),
        "C_H3_VU_LOCAL_BURST": b0_vu & mbv_ok & (study_df["burst_count"] >= 1),
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

            summary_rows.append({
                "study_mode": study_mode,
                "group": g_name,
                "horizon_days": int(h),
                "raw_events": n_raw,
                "effective_events": n_eff,
                "mean_return": mean_ret,
                "median_return": med_ret,
                "win_rate": win_rate,
                "mean_mfe": mean_mfe,
                "mean_mae": mean_mae,
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
    )
    d_h2 = match_controls_same_date_rvol(
        study_df,
        groups["C_H2_ABU_OFFSETTING_MBV"],
        rvol_buckets=rvol_buckets,
        outcome_col=f"mae_{primary_h}d",
        min_events=min_events_per_group,
    )

    # Group E: Permutation negative control inside B0_EU
    e_perm = permutation_negative_control(
        study_df,
        "B0_EU" if "B0_EU" in study_df.columns else "feature_status",
        mbv_share_cut=mbv_share_cut,
        outcome_col=f"fwd_ret_{primary_h}d",
        min_events=min_events_per_group,
    )

    # Calendar-block bootstrap on MBV_OK baseline sessions / primary events when coverage suffices
    boot_target = study_df.loc[
        groups["B_MBV_BULL_BURST_ONLY"] & study_df[f"fwd_ret_{primary_h}d"].notna(),
        ["trade_date", f"fwd_ret_{primary_h}d"],
    ].rename(columns={"trade_date": "date", f"fwd_ret_{primary_h}d": "return"})

    bootstrap_status = "OK"
    bootstrap_detail = ""
    bootstrap_df = pd.DataFrame()
    valid_blocks = [b for b in bootstrap_blocks if 2 * int(b) <= len(cal_list)]
    if boot_target.empty or not valid_blocks:
        bootstrap_status = "INCONCLUSIVE"
        bootstrap_detail = "Insufficient event coverage or short evaluation calendar for block bootstrap"
    else:
        try:
            bootstrap_df = run_calendar_block_bootstrap(
                boot_target,
                trading_calendar=cal_list,
                block_lengths=valid_blocks,
                repetitions=bootstrap_repetitions,
                seed=bootstrap_seed,
                confidence=confidence,
                vlr_dir=vlr_dir,
            )
        except ValueError as exc:
            bootstrap_status = "INCONCLUSIVE"
            bootstrap_detail = str(exc)

    feature_status_counts = study_df["feature_status"].value_counts(dropna=False).to_dict()
    fill_status_counts = study_df["t1_fill_status"].value_counts(dropna=False).to_dict()

    return {
        "study_mode": study_mode,
        "research_grade": "PROVISIONAL_RESEARCH" if study_mode != "SYNTHETIC_DEMO" else "SYNTHETIC_DEMO_ONLY",
        "vlr_parity_status": "TDX_PARITY_NOT_VERIFIED",
        "calendar_sessions": len(cal_list),
        "total_panel_rows": len(study_df),
        "feature_status_counts": feature_status_counts,
        "t1_fill_status_counts": fill_status_counts,
        "group_summary": summary_df,
        "matched_control_h1": d_h1,
        "matched_control_h2": d_h2,
        "permutation_control_e": e_perm,
        "bootstrap_status": bootstrap_status,
        "bootstrap_detail": bootstrap_detail,
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
    )
    lines = [
        f"# MBV V0.1 Event Study Report (`{mode}`)",
        "",
        banner,
        "## 1. Sample Coverage & Attrition",
        f"- **Evaluation Calendar Sessions**: `{study_result['calendar_sessions']}`",
        f"- **Total Daily Panel Rows**: `{study_result['total_panel_rows']}`",
        f"- **MBV `feature_status` Counts**: `{study_result['feature_status_counts']}`",
        f"- **T+1 `fill_status` Counts**: `{study_result['t1_fill_status_counts']}`",
        "",
        "## 2.Matched & Permutation Controls (Groups D & E)",
        f"- **H1 Matched Control (Same-Date + RVOL Bucket)**: `{study_result['matched_control_h1']}`",
        f"- **H2 Matched Control (Same-Date + RVOL Bucket)**: `{study_result['matched_control_h2']}`",
        f"- **Group E Permutation Negative Control**: `{study_result['permutation_control_e']}`",
        "",
        "## 3. Calendar-Block Bootstrap (`verify/inference.py`)",
        f"- **Bootstrap Status**: `{study_result['bootstrap_status']}` {study_result['bootstrap_detail']}",
    ]
    bdf: pd.DataFrame = study_result["bootstrap_table"]
    if not bdf.empty:
        lines.append("")
        lines.append(bdf.to_string(index=False))

    lines.extend([
        "",
        "## 4. Group × Horizon Summary",
        "",
        study_result["group_summary"].to_string(index=False),
        "",
    ])
    return "\n".join(lines)
