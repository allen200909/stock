"""Command-line interface and end-to-end pipeline orchestrator for MBV V0.1."""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any, Optional, Sequence

import pandas as pd
import yaml

from mbv.adapters import (
    _read_table,
    generate_synthetic_market_bundle,
    load_daily_bars,
    load_minute_bars,
    write_table,
)
from mbv.aggregate import aggregate_daily_features
from mbv.baselines import build_tod_baseline, compute_session_ema_benchmark
from mbv.event_study import format_study_markdown_report, run_event_study
from mbv.features import detect_bursts
from mbv.join import (
    assert_frozen_vlr_integrity,
    compute_readonly_b0,
    join_daily_vlr_mbv,
)
from mbv.schema import (
    DataContractError,
    assert_no_future_columns,
    compute_dataframe_hash,
    compute_params_hash,
)
from mbv.sessions import expected_slot_count, validate_minute_bars


def load_config(config_path: Optional[str | Path] = None) -> dict[str, Any]:
    if config_path is None:
        default_p = Path(__file__).resolve().parent.parent / "config" / "default.yaml"
        if default_p.exists():
            config_path = default_p
    if config_path is None:
        return {}
    p = Path(config_path)
    if not p.exists():
        raise FileNotFoundError(f"Configuration file not found: {p}")
    with p.open("r", encoding="utf-8") as fh:
        cfg = yaml.safe_load(fh) or {}
    return cfg


def compute_mbv_daily_pipeline(
    minute_df: pd.DataFrame,
    *,
    config: Optional[dict[str, Any]] = None,
    daily_ref: Optional[pd.DataFrame] = None,
    trading_calendar: Optional[Any] = None,
) -> pd.DataFrame:
    """End-to-end causal pipeline: validated minute bars -> past-only TOD baseline -> bursts -> daily features.

    Input contract (WP-B): ``minute_df`` must already be in **normalized `bar_start` semantics with volume in
    shares** (i.e. the output of :func:`mbv.sessions.validate_minute_bars` / :func:`mbv.adapters.load_minute_bars`).
    The pipeline re-validates it here with ``semantics='bar_start'`` and ``volume_unit='share'`` (idempotent on
    normalized data) at the configured frequency, so raw or unvalidated bars (lunch-break / off-grid / bar_end
    boundary bars, bad OHLC, negative or non-finite volume, duplicate keys) fail closed with
    :class:`DataContractError` instead of entering the main chain. Raw `bar_end` sources must be normalized upstream
    via ``load_minute_bars(..., semantics='bar_end')``.

    ``trading_calendar`` (optional, ordered unique exchange sessions) makes the 20-session baseline window step on
    the exchange calendar rather than on sessions present in the data, so missing sessions occupy a window step.
    """
    cfg = config or {}
    dc = cfg.get("data_contract", {})
    bc = cfg.get("baseline", {})
    fc = cfg.get("burst", {})

    freq = dc.get("frequency", "5min")
    excl_close = bool(dc.get("exclude_closing_auction", False))
    min_cov = float(dc.get("min_slot_coverage", 0.95))
    recon_tol = float(dc.get("reconciliation_tol", 0.02))

    method = bc.get("method", "tod_median")
    lookback = int(bc.get("lookback_days", 20))
    min_hist = int(bc.get("min_history_days", 15))

    rel_th = float(fc.get("rel_vol_threshold", 2.5))
    eff_th = float(fc.get("body_eff_threshold", 0.10))
    tick = float(fc.get("tick_size", 0.01))
    cap_mult = float(fc.get("ratio_cap_multiple", 10.0))
    dir_eps = float(fc.get("dir_day_eps", 1e-6))

    minute_df = validate_minute_bars(
        minute_df,
        semantics="bar_start",
        frequency=freq,
        tz=dc.get("timezone", "Asia/Shanghai"),
        volume_unit="share",
        amount_unit="cny",
    )

    if method == "tod_median":
        base_df = build_tod_baseline(
            minute_df, lookback_days=lookback, min_history_days=min_hist, trading_calendar=trading_calendar
        )
    elif method == "session_ema":
        span = int(bc.get("session_ema_span", 20))
        base_df = compute_session_ema_benchmark(minute_df, span=span, min_periods=min(10, span))
    else:
        raise DataContractError(f"Unknown baseline.method '{method}'")

    burst_df = detect_bursts(
        minute_df,
        base_df,
        rel_vol_threshold=rel_th,
        body_eff_threshold=eff_th,
        tick_size=tick,
        lookback_days=lookback,
        min_history_days=min_hist,
    )

    daily_features = aggregate_daily_features(
        burst_df,
        frequency=freq,
        exclude_closing_auction=excl_close,
        min_slot_coverage=min_cov,
        rel_vol_threshold=rel_th,
        ratio_cap_multiple=cap_mult,
        daily_ref=daily_ref,
        reconciliation_tol=recon_tol,
        dir_day_eps=dir_eps,
    )
    assert_no_future_columns(daily_features)
    return daily_features


def cmd_inspect_data(args: argparse.Namespace) -> int:
    cfg = load_config(args.config)
    dc = cfg.get("data_contract", {})
    freq = dc.get("frequency", "5min")

    min_df, meta = load_minute_bars(
        args.minute,
        frequency=freq,
        semantics=dc.get("timestamp_semantics", "bar_start"),
        tz=dc.get("timezone", "Asia/Shanghai"),
        volume_unit=dc.get("volume_unit", "share"),
        amount_unit=dc.get("amount_unit", "cny"),
        adjustment=dc.get("adjustment", "unadjusted"),
    )
    day_df = load_daily_bars(
        args.daily,
        volume_unit=dc.get("volume_unit", "share"),
        amount_unit=dc.get("amount_unit", "cny"),
    )
    exp_slots = expected_slot_count(freq, exclude_closing_auction=False)
    slot_counts = min_df.groupby(["symbol", "trade_date"]).size()

    summary = {
        "status": "INSPECT_OK",
        "frequency": freq,
        "expected_slots_per_session": exp_slots,
        "minute_rows": int(len(min_df)),
        "minute_symbols": sorted(min_df["symbol"].unique().tolist()),
        "minute_sessions": int(len(slot_counts)),
        "min_slots_observed": int(slot_counts.min()),
        "max_slots_observed": int(slot_counts.max()),
        "daily_rows": int(len(day_df)),
        "source_hash": meta.source_hash,
    }
    print(json.dumps(summary, indent=2, ensure_ascii=False))
    return 0


def cmd_compute_features(args: argparse.Namespace) -> int:
    cfg = load_config(args.config)
    dc = cfg.get("data_contract", {})
    min_df, _ = load_minute_bars(
        args.minute,
        frequency=dc.get("frequency", "5min"),
        semantics=dc.get("timestamp_semantics", "bar_start"),
        tz=dc.get("timezone", "Asia/Shanghai"),
        volume_unit=dc.get("volume_unit", "share"),
        amount_unit=dc.get("amount_unit", "cny"),
        adjustment=dc.get("adjustment", "unadjusted"),
    )
    cal_df = _read_table(args.calendar) if getattr(args, "calendar", None) else None
    feat_df = compute_mbv_daily_pipeline(min_df, config=cfg, trading_calendar=cal_df)
    out_p = write_table(feat_df, args.out)
    print(f"Wrote {len(feat_df)} daily MBV rows to {out_p}")
    return 0


def cmd_join_vlr(args: argparse.Namespace) -> int:
    cfg = load_config(args.config)
    dc = cfg.get("data_contract", {})
    day_df = load_daily_bars(
        args.daily,
        volume_unit=dc.get("volume_unit", "share"),
        amount_unit=dc.get("amount_unit", "cny"),
    )
    b0_df = compute_readonly_b0(
        day_df,
        initial_tr=cfg.get("vlr_b0", {}).get("initial_tr", "hl"),
    )
    feat_df = _read_table(args.features)
    joined = join_daily_vlr_mbv(
        b0_df,
        feat_df,
        source_hash=compute_dataframe_hash(day_df),
        params_hash=compute_params_hash(cfg),
        reconciliation_tol=float(dc.get("reconciliation_tol", 0.02)),
        dir_day_eps=float(cfg.get("burst", {}).get("dir_day_eps", 1e-6)),
    )
    out_p = write_table(joined, args.out)
    print(f"Wrote {len(joined)} joined B0+MBV rows to {out_p}")
    return 0


def cmd_study(args: argparse.Namespace) -> int:
    cfg = load_config(args.config)
    ec = cfg.get("event_study", {})
    joined_df = _read_table(args.joined)
    cal_df = _read_table(args.calendar)

    study_mode = cfg.get("study_mode", "SYNTHETIC_DEMO")
    res = run_event_study(
        joined_df,
        trading_calendar=cal_df,
        study_mode=study_mode,
        horizons=ec.get("horizons", [1, 3, 5, 10, 20]),
        min_events_per_group=int(ec.get("min_events_per_group", 5)),
        mbv_share_cut=float(ec.get("mbv_share_cut", 0.15)),
        mbv_dominance_cut=float(ec.get("mbv_dominance_cut", 0.25)),
        mbv_abs_dom_weak_cut=float(ec.get("mbv_abs_dom_weak_cut", 0.25)),
        rvol_buckets=ec.get("rvol_buckets", [0.0, 1.2, 1.5, 2.2, 3.0, 100.0]),
        bootstrap_blocks=ec.get("bootstrap_blocks", [5, 10, 20]),
        bootstrap_repetitions=int(ec.get("bootstrap_repetitions", 500)),
        bootstrap_seed=int(ec.get("bootstrap_seed", 20261013)),
        confidence=float(ec.get("confidence", 0.95)),
    )

    outdir = Path(args.outdir)
    outdir.mkdir(parents=True, exist_ok=True)
    res["group_summary"].to_csv(outdir / "group_summary.csv", index=False)
    res["outcomes_table"].to_csv(outdir / "forward_outcomes_labels.csv", index=False)
    if not res["bootstrap_table"].empty:
        res["bootstrap_table"].to_csv(outdir / "bootstrap_summary.csv", index=False)
    md = format_study_markdown_report(res)
    (outdir / "study_report.md").write_text(md, encoding="utf-8")
    print(f"[{study_mode}] Wrote event study artifacts to {outdir}")
    return 0


def run_synthetic_demo_workflow(
    *,
    examples_dir: str | Path,
    outdir: str | Path,
    config_path: Optional[str | Path] = None,
) -> dict[str, Any]:
    """Self-contained deterministic `SYNTHETIC_DEMO` workflow producing CSV fixtures, joined features & study report."""
    cfg = load_config(config_path)
    cfg["study_mode"] = "SYNTHETIC_DEMO"
    ex_dir = Path(examples_dir)
    out_dir = Path(outdir)
    ex_dir.mkdir(parents=True, exist_ok=True)
    out_dir.mkdir(parents=True, exist_ok=True)

    bundle = generate_synthetic_market_bundle(
        symbols=("600000.SH", "000001.SZ", "300750.SZ"),
        n_sessions=170,
        minute_tail_sessions=45,
        frequency="5min",
        seed=20261111,
    )
    min_csv = ex_dir / "synthetic_minute_5m.csv"
    day_csv = ex_dir / "synthetic_daily.csv"
    cal_csv = ex_dir / "synthetic_calendar.csv"
    bundle["minute"].to_csv(min_csv, index=False)
    bundle["daily"].to_csv(day_csv, index=False)
    bundle["calendar"].to_csv(cal_csv, index=False)

    min_df, meta = load_minute_bars(min_csv, frequency="5min", semantics="bar_start", source="SYNTHETIC_DEMO")
    day_df = load_daily_bars(day_csv)
    vlr_hashes = assert_frozen_vlr_integrity()
    b0_df = compute_readonly_b0(day_df)
    mbv_df = compute_mbv_daily_pipeline(
        min_df, config=cfg, daily_ref=b0_df, trading_calendar=bundle["calendar"]
    )
    joined_df = join_daily_vlr_mbv(
        b0_df,
        mbv_df,
        source_hash=meta.source_hash,
        params_hash=compute_params_hash(cfg),
        reconciliation_tol=float(cfg.get("data_contract", {}).get("reconciliation_tol", 0.02)),
        dir_day_eps=float(cfg.get("burst", {}).get("dir_day_eps", 1e-6)),
    )
    # Invariant: T-day confirmed B0 records must neither disappear nor duplicate through the join.
    if len(joined_df) != len(b0_df):
        raise DataContractError("Joined table row count differs from B0 table")
    for ev in ("B0_EU", "B0_ABU", "B0_VU", "B0_ED", "B0_ABD", "B0_VD"):
        if ev in b0_df.columns and int(joined_df[ev].astype(bool).sum()) != int(b0_df[ev].astype(bool).sum()):
            raise DataContractError(f"B0 event count changed through join for {ev}")

    outputs: dict[str, Path] = {
        "mbv_daily_features": out_dir / "mbv_daily_features.csv",
        "joined_vlr_mbv": out_dir / "joined_vlr_mbv.csv",
    }
    mbv_df.to_csv(outputs["mbv_daily_features"], index=False)
    joined_df.to_csv(outputs["joined_vlr_mbv"], index=False)

    ec = cfg.get("event_study", {})
    study_res = run_event_study(
        joined_df,
        trading_calendar=bundle["calendar"],
        study_mode="SYNTHETIC_DEMO",
        horizons=ec.get("horizons", [1, 3, 5, 10, 20]),
        min_events_per_group=int(ec.get("min_events_per_group", 5)),
        mbv_share_cut=float(ec.get("mbv_share_cut", 0.15)),
        mbv_dominance_cut=float(ec.get("mbv_dominance_cut", 0.25)),
        mbv_abs_dom_weak_cut=float(ec.get("mbv_abs_dom_weak_cut", 0.25)),
        rvol_buckets=ec.get("rvol_buckets", [0.0, 1.2, 1.5, 2.2, 3.0, 100.0]),
        bootstrap_blocks=ec.get("bootstrap_blocks", [5, 10, 20]),
        bootstrap_repetitions=int(ec.get("bootstrap_repetitions", 500)),
        bootstrap_seed=int(ec.get("bootstrap_seed", 20261013)),
        confidence=float(ec.get("confidence", 0.95)),
    )
    outputs["group_summary"] = out_dir / "group_summary.csv"
    outputs["forward_outcomes_labels"] = out_dir / "forward_outcomes_labels.csv"
    study_res["group_summary"].to_csv(outputs["group_summary"], index=False)
    study_res["outcomes_table"].to_csv(outputs["forward_outcomes_labels"], index=False)
    if not study_res["bootstrap_table"].empty:
        outputs["bootstrap_summary"] = out_dir / "bootstrap_summary.csv"
        study_res["bootstrap_table"].to_csv(outputs["bootstrap_summary"], index=False)
    report_md = format_study_markdown_report(study_res)
    report_path = out_dir / "study_report.md"
    report_path.write_text(report_md, encoding="utf-8")
    outputs["study_report"] = report_path

    parquet_status = "WRITTEN"
    try:
        mbv_df.to_parquet(out_dir / "mbv_daily_features.parquet", index=False)
        joined_df.to_parquet(out_dir / "joined_vlr_mbv.parquet", index=False)
    except ImportError:
        parquet_status = "SKIPPED_NO_PARQUET_ENGINE"

    ok_mask = mbv_df["feature_status"] == "OK"
    summary = {
        "study_mode": "SYNTHETIC_DEMO",
        "minute_rows": int(len(min_df)),
        "daily_rows": int(len(day_df)),
        "mbv_rows": int(len(mbv_df)),
        "joined_rows": int(len(joined_df)),
        "mbv_feature_status_counts": {k: int(v) for k, v in mbv_df["feature_status"].value_counts().items()},
        "joined_feature_status_counts": {k: int(v) for k, v in joined_df["feature_status"].value_counts().items()},
        "burst_regime_counts": {k: int(v) for k, v in mbv_df["burst_regime"].value_counts().items()},
        "ok_days_with_bursts": int((mbv_df.loc[ok_mask, "burst_count"] > 0).sum()),
        "ok_days_mean_burst_share": float(mbv_df.loc[ok_mask, "burst_share"].mean()) if ok_mask.any() else None,
        "b0_event_counts": {
            ev: int(joined_df[ev].astype(bool).sum())
            for ev in ("B0_EU", "B0_ABU", "B0_VU", "B0_ED", "B0_ABD", "B0_VD") if ev in joined_df.columns
        },
        "parquet": parquet_status,
    }
    manifest = build_run_manifest(
        cfg=cfg,
        inputs={"minute": min_csv, "daily": day_csv, "calendar": cal_csv},
        outputs=outputs,
        vlr_hashes=vlr_hashes,
        summary=summary,
        seed=20261111,
    )
    manifest_path = out_dir / "run_manifest.json"
    manifest_path.write_text(json.dumps(manifest, indent=2, ensure_ascii=False, sort_keys=True), encoding="utf-8")

    return {
        **summary,
        "feature_status_counts": study_res["feature_status_counts"],
        "vlr_reference_hashes": vlr_hashes,
        "report_path": str(report_path),
        "manifest_path": str(manifest_path),
    }


def _sha256_file(path: Path) -> str:
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def build_run_manifest(
    *,
    cfg: dict[str, Any],
    inputs: dict[str, Path],
    outputs: dict[str, Path],
    vlr_hashes: dict[str, str],
    summary: dict[str, Any],
    seed: int,
) -> dict[str, Any]:
    """Reproducibility manifest: config/params hash, input & output SHA-256, MBV code hashes, environment.

    Deliberately excludes wall-clock timestamps so that two runs with identical code/config/seed produce a
    byte-identical manifest.
    """
    import numpy as _np
    import platform

    pkg_root = Path(__file__).resolve().parent
    code_hashes = {p.name: _sha256_file(p) for p in sorted(pkg_root.glob("*.py"))}
    return {
        "study_mode": "SYNTHETIC_DEMO",
        "synthetic_seed": seed,
        "config": cfg,
        "params_hash": compute_params_hash(cfg),
        "inputs_sha256": {k: _sha256_file(v) for k, v in inputs.items()},
        "outputs_sha256": {k: _sha256_file(v) for k, v in outputs.items()},
        "mbv_code_sha256": code_hashes,
        "frozen_vlr_reference_sha256": vlr_hashes,
        "environment": {
            "python": platform.python_version(),
            "pandas": pd.__version__,
            "numpy": _np.__version__,
            "pyyaml": getattr(yaml, "__version__", "unknown"),
        },
        "summary": summary,
        "gates": {
            "G0_code": "SEE reports/R6_ACCEPTANCE_REPORT.md",
            "G1_real_minute_data": "BLOCKED_REAL_DATA",
            "G2_tdx_b0_parity": "NOT_VERIFIED",
            "G3_real_event_study": "NOT_TESTED",
        },
    }


def cmd_demo(args: argparse.Namespace) -> int:
    info = run_synthetic_demo_workflow(
        examples_dir=args.examples_dir,
        outdir=args.outdir,
        config_path=args.config,
    )
    print(json.dumps(info, indent=2, ensure_ascii=False))
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="mbv.cli",
        description="MBV V0.1 — VLR × Microburst Validation Layer offline research CLI",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    p_ins = sub.add_parser("inspect-data", help="Validate minute & daily inputs against data contract")
    p_ins.add_argument("--minute", required=True, help="Path to minute CSV/Parquet")
    p_ins.add_argument("--daily", required=True, help="Path to daily CSV/Parquet")
    p_ins.add_argument("--config", default=None, help="Path to YAML config")
    p_ins.set_defaults(func=cmd_inspect_data)

    p_feat = sub.add_parser("compute-features", help="Compute lagged TOD baselines and daily MBV features")
    p_feat.add_argument("--minute", required=True, help="Path to minute CSV/Parquet")
    p_feat.add_argument("--config", default=None, help="Path to YAML config")
    p_feat.add_argument("--out", required=True, help="Output CSV/Parquet path")
    p_feat.add_argument(
        "--calendar", default=None,
        help="Optional exchange trading calendar CSV/Parquet (trade_date); baseline window steps on it",
    )
    p_feat.set_defaults(func=cmd_compute_features)

    p_join = sub.add_parser("join-vlr", help="Compute read-only B0 and left-join daily MBV features")
    p_join.add_argument("--daily", required=True, help="Path to daily OHLCV CSV/Parquet")
    p_join.add_argument("--features", required=True, help="Path to MBV daily features CSV/Parquet")
    p_join.add_argument("--config", default=None, help="Path to YAML config")
    p_join.add_argument("--out", required=True, help="Output joined CSV/Parquet path")
    p_join.set_defaults(func=cmd_join_vlr)

    p_study = sub.add_parser("study", help="Run calendar-gated T+1 event study, controls & bootstrap")
    p_study.add_argument("--joined", required=True, help="Path to joined B0+MBV CSV/Parquet")
    p_study.add_argument("--calendar", required=True, help="Path to explicit trading calendar CSV/Parquet")
    p_study.add_argument("--config", default=None, help="Path to YAML config")
    p_study.add_argument("--outdir", required=True, help="Directory for study outputs")
    p_study.set_defaults(func=cmd_study)

    p_demo = sub.add_parser("demo", help="Generate deterministic synthetic data and run full SYNTHETIC_DEMO")
    p_demo.add_argument("--examples-dir", default="examples", help="Directory for synthetic input CSVs")
    p_demo.add_argument("--outdir", default="examples/demo_outputs", help="Directory for demo outputs")
    p_demo.add_argument("--config", default=None, help="Path to YAML config")
    p_demo.set_defaults(func=cmd_demo)

    return parser


def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    return int(args.func(args))


if __name__ == "__main__":
    raise SystemExit(main())
