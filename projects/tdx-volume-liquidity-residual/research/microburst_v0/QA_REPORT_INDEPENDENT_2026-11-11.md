# Independent QA audit — MBV V0.1 Claude Code deliverable (2026-11-11)

**Decision: FAIL G0 / NOT ACCEPTED.** The provided ZIP has been preserved in the development branch as a **WIP prototype** for traceability, not promoted as a research-ready engine or merged into `master`.

## Input and environment

- User-supplied archive: `MBV_V0.1_Deliverables.zip`
- Archive SHA-256: `bc697479081f40a82b795f289099ee87d19a1af718a8edddb02edc8917441c2e`
- Source: six Python files, one pytest file, one development log. `__pycache__/*.pyc` and generated cache/coverage files excluded from repository.
- Local independent execution: Linux, Python 3.13.5, pytest 9.0.2, pandas 2.2.3, numpy 2.3.5.
- Command: `PYTHONPATH=. python -m pytest -v tests/test_features.py` => **1 passed**, not 20 tests.
- Command: `PYTHONPATH=. python -m pytest --cov=mbv --cov-report=term-missing -q` => **1 passed**, total statement coverage **12%** (49 statements, 43 uncovered).
- The passing test is a simple volume-threshold smoke test, **not** the plan's T01 historical-baseline non-leakage test.

## Independently reproduced defects (synthetic probes)

1. **P0 — Future leakage, T01/T02:** `compute_tod_baseline()` groups all supplied days and ignores `lookback_days`. A single 09:30 bar with volume 100 produces baseline 100; appending *tomorrow's* 09:30 bar with volume 10,000 changes that earlier baseline to **5,050**. There is no prior-day-only rolling median or `min_history_days=15` gate.
2. **P0 — Cross-symbol contamination, T03:** volume 100 for symbol A plus volume 10,000 for symbol B at the same 09:30 slot yields **5,050**, instead of keeping symbol A's baseline separate.
3. **P0 — Session and invalid synthetic bars, T04/T07:** adapter ignores the supplied filepath, creates a 240-minute continuous series on **2026-01-01** (not an A-share trading day), crossing the 11:30–13:00 lunch break (**90** synthesized rows). With independently sampled O/H/L/C, only approximately **5%** of generated bars satisfied standard OHLC bounds in one unseeded run. It is not a valid or reproducible A-share demo.
4. **P0 — Incomplete burst definition:** `detect_bursts()` tests volume ratio alone; a 500-volume bar vs 100 baseline is flagged even with `open=close`, whereas plan §4.2 requires `abs((C-O)/(H-L)) >= 0.10`.
5. **P0 — Zero baseline:** dividing positive volume by a zero baseline yields `inf`; `BASELINE_INVALID` is missing.
6. **P0 — Missing status conflated with no burst:** `aggregate_daily_features()` returns `burst_share=0` for zero total volume, not `NO_VOLUME` with unavailable feature values.
7. **P0 — Duplicate join keys, T14:** one B0 row joined to two MBV rows with the same (symbol, trade_date) results in **two output rows**; missing duplicate-key validation / `many_to_one` enforcement.
8. **P1 — Unimplemented mandatory outputs:** daily aggregation returns only `burst_count` and `burst_share`. `peak_ratio`, `burst_dominance`, `burst_concentration`, `burst_direction_agreement`, coverage, reconciliation and status are absent. Dataclasses are definitions, not validation functions.
9. **P1 — Missing pipeline:** no real CSV/Parquet adapter, no QMT/PTADE import contract, no actual VLR B0 invocation, event study, matched controls, CLI, benchmark, experiment reports, QA matrix or reproducible example.

The left join **does preserve** B0 rows with no MBV match in a simple one-to-one fixture, but no missing-feature status is supplied. The presence of this one behavior does not satisfy full T12.

## T01–T20 original acceptance matrix

| ID | Result | Audit evidence |
|---|---|---|
| T01 | FAIL | Future bar changes earlier slot baseline |
| T02 | FAIL | All-sample baseline violates prefix invariance |
| T03 | FAIL | Different symbols share same baseline |
| T04 | FAIL | Synthetic minutes include lunch break |
| T05 | NOT RUN / NOT IMPLEMENTED | Start/end timestamp adapter absent |
| T06 | FAIL | Generator does not produce valid A-share 1m/5m session structure |
| T07 | FAIL | Zero baseline creates inf; no negative/duplicate validation |
| T08 | NOT IMPLEMENTED | Coverage and status gating absent |
| T09 | NOT IMPLEMENTED | Minimum prior-day baseline history absent |
| T10 | NOT IMPLEMENTED | Direction/HHI aggregation absent |
| T11 | NOT IMPLEMENTED | No validated burst vs uniform test |
| T12 | PARTIAL | Left join keeps row; required missing status absent |
| T13 | NOT IMPLEMENTED | Corporate action/limit/suspension status absent |
| T14 | FAIL | Duplicate MBV keys multiply B0 rows |
| T15 | NOT RUN | No actual B0 API integration or regression test |
| T16 | NOT IMPLEMENTED | No event-research execution calendar gate |
| T17 | NOT IMPLEMENTED | No event/forward-return pipeline |
| T18 | NOT IMPLEMENTED | No control matching |
| T19 | NOT IMPLEMENTED | No calendar-block bootstrap integration |
| T20 | NOT IMPLEMENTED | No reproducible synthetic research report |

**These results are from independent code inspection and the specified probes; do not relabel unrun rows as passing test cases.**

## Gate determination

- **G0: FAIL.** Mandatory code safety, schema, deterministic synthetic source, past-only baseline, quality statuses, and complete tests missing.
- **G1: BLOCKED_REAL_DATA.** No verified QMT/PTADE minute data, provenance or reconciliation.
- **G2: NOT VERIFIED.** Authentic TDX full-21-series parity remains outstanding in the parent VLR project.
- **G3: NOT TESTED.** No real matched-control OOS performance result.

## Corrective instructions for Claude Code

1. Treat this as a WIP checkpoint, **not** a completed V0.1. Begin by fixing leakage, symbol separation, A-share session & timestamp handling, OHLC/volume validation, zero baselines and duplicate join keys.
2. Implement §4.2 body-efficiency gating and all §4.3 aggregate outputs and statuses, with min-history/coverage/reconciliation rules.
3. Implement B0 read-only adapter, deterministic minute fixtures, one-command CLI, synthetic event study and `SYNTHETIC_DEMO` reporting; no invented real-world findings.
4. Replace the current single smoke test with the full T01–T20 actual automated suite, preserving existing baseline tests.
5. Submit all code and actual test logs on `feature/vlr-microburst-v0`. Never edit frozen V2.1.2 indicator/selectors or merge `master` without review.

## Reproduction snippets

Run from this directory with `PYTHONPATH=.`:

```python
import pandas as pd
from mbv.baselines import compute_tod_baseline
from mbv.join import join_daily_vlr_mbv

a = pd.DataFrame({"symbol":["A"], "ts":pd.to_datetime(["2026-01-05 09:30"]), "volume":[100.]})
future = pd.DataFrame({"symbol":["A"], "ts":pd.to_datetime(["2026-01-06 09:30"]), "volume":[10000.]})
other = future.copy(); other["symbol"]="B"; other["ts"]=a["ts"].iloc[0]
assert compute_tod_baseline(a).iloc[0] == 100.
assert compute_tod_baseline(pd.concat([a,future])).iloc[0] == 5050.  # demonstrates future leakage
assert compute_tod_baseline(pd.concat([a,other])).iloc[0] == 5050.   # demonstrates symbol leakage
b0 = pd.DataFrame({"symbol":["A"],"trade_date":["2026-01-05"]})
mbv = pd.DataFrame({"symbol":["A","A"],"trade_date":["2026-01-05"]*2,"burst_count":[1,2]})
assert len(join_daily_vlr_mbv(b0,mbv)) == 2  # demonstrates one-to-many explosion
```

No claim of valid research signal or alpha is supported by this checkpoint.
