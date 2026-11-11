# Carbon completion archive — Independent round-2 QA (2026-11-11)

**Verdict: G0 FAIL — NOT ACCEPTED / WIP ONLY.** This review concerns the uploaded `MBV_V0.1_Carbon_Completed.zip`; the previous VLR V2.1.2 baseline remains frozen. Do not merge to `master` or use the prototype for research signals.

## Artifact and reproduction

- Archive SHA256: `aec596a0fadd9143deffc280f3b0c8427299300d078efc3c063933e094d5ecdd`.
- ZIP has **21 entries** including **3 MBV Python source modules** (`mbv/adapters.py`, `mbv/features.py`, `mbv/aggregate.py`), a single test file with two tests, docs, frozen VLR reference files, and Python caches. The archive entry paths use Windows backslashes (`\\`), which may not unpack as intended on POSIX systems.
- Independent environment: Linux; Python **3.13.5**; pytest **9.0.2**; pandas and NumPy installed.
- Command from normalized extract directory: `PYTHONPATH=. python -m pytest -v tests/test_features.py` -> **2 passed**.
- Command: `PYTHONPATH=. pytest --cov=mbv --cov-report=term-missing -q` -> **2 passed**, **36% statement coverage** (39 statements, 25 missed). `aggregate.py`: **0%**.
- **Crucial**: `test_t01_no_future_leakage` ends with `assert True`, does not exercise the actual past-only baseline and is a false-positive T01 acceptance test. `test_t07_invalid_ohlc` does correctly reject a malformed price range, but does not cover T07 fully.

## Independently reproduced critical defects

1. **T01/T02 future leakage**: `mbv.adapters.build_tod_baseline` uses `df.groupby(df['ts'].dt.time)['volume'].median()` across ALL rows with no past-only window and ignores `lookback_days`. One Monday 09:30 volume 100 yields baseline 100; after adding Tuesday 09:30 volume 10,000, the shared baseline becomes **5,050**.
2. **T03 cross-ticker contamination**: a different symbol's 09:30 volume 10,000 changes original ticker 09:30 baseline from 100 to **5,050**.
3. **T07 invalid values**: positive volume over a zero baseline produces `rel_vol=inf` and `is_burst=True`. `validate_minute_bars` accepts negative volumes and NaN volumes, and lacks duplicate (symbol,ts) checks.
4. **T04/T05/T06 session normalization**: `validate_minute_bars` rejects some lunch timestamps but accepts **08:00** (outside any valid A-share trading slot). It does not implement 1m/5m valid slot sets, bar_end semantics, symbol-scoped duplicate validation, or 240/48-slot count and coverage gates.
5. **T08 zero volume status**: `aggregate_daily_features` sets `feature_status='NO_VOLUME'` but still emits `burst_count=0` and `burst_share=0`; the spec requires unavailable values to be `NaN`, avoiding conflation with no-burst days.
6. **T10 incomplete daily metrics**: aggregation produces only `burst_count`, `burst_share` and `feature_status`. Missing `peak_ratio`, weighted `burst_dominance`, HHI-style `burst_concentration`, `single_burst_flag`, `burst_direction_agreement`, `valid_slot_coverage` and reconciliation.
7. **Missing mandatory modules**: the archive has no `mbv/schema.py`, `mbv/baselines.py`, `mbv/join.py`, `mbv/sessions.py` or CLI; no real-data adapter, B0 integration or event-study implementation.

**Positive change verified:** `detect_bursts` now applies body-efficiency gating: a flat-body bar (E=0) with 10x volume is correctly **not** flagged. It still needs strict baseline validity and finite-value protection.

## T01–T20 acceptance (original numbered plan)

| Test | Status | Reason |
|---|---|---|
| T01 | FAIL | Historical baseline contaminated by future input; supplied test `assert True` is non-validating |
| T02 | FAIL | Baseline output is not prefix-invariant |
| T03 | FAIL | Ticker cross-contamination |
| T04 | PARTIAL / FAIL | Lunch rejection exists but outside-session timestamps accepted |
| T05 | NOT IMPLEMENTED | Bar-start vs bar-end normalized semantics |
| T06 | NOT IMPLEMENTED | Valid 1m/5m session-slot/coverage checks |
| T07 | PARTIAL / FAIL | Invalid OHLC rejected; negative/NaN volume, duplicate timestamps and zero baseline not handled |
| T08 | FAIL | No coverage gate; NO_VOLUME uses zero instead of unavailable |
| T09 | FAIL | Minimum prior history gate absent |
| T10 | FAIL | Direction/concentration/one-burst outputs absent |
| T11 | NOT RUN / NOT IMPLEMENTED | No valid burst-versus-uniform fixture |
| T12 | NOT IMPLEMENTED | Left join/status for missing minute data absent |
| T13 | NOT IMPLEMENTED | Corporate-action/limit/suspension flags |
| T14 | NOT IMPLEMENTED | Unique B0/MBV key guard; join module missing |
| T15 | NOT RUN | No B0 read-only bridge test |
| T16 | NOT IMPLEMENTED | No event-research calendar gate |
| T17 | NOT IMPLEMENTED | No T feature / future-label data isolation pipeline |
| T18 | NOT IMPLEMENTED | No matched controls or INCONCLUSIVE handling |
| T19 | NOT IMPLEMENTED | No calendar-block bootstrap integration |
| T20 | NOT IMPLEMENTED | No one-command reproducible SYNTHETIC_DEMO report |

No T01–T20 full acceptance evidence was presented. Two passing tests **cannot** be described as passing the 20-test matrix.

## Gate decision and handoff

- **G0 FAILED**. Fix causal baseline and robust data-contract validation first.
- **G1 BLOCKED_REAL_DATA**. No audited QMT/PTADE real minute OHLCV, adjustments or exchange calendar.
- **G2 NOT VERIFIED**. Original authentic 21-series TongDaXin ↔ Python B0 parity still pending.
- **G3 NOT TESTED**. No real matched-controls or untouched OOS study.

**Next Carbon task, fully offline**:

1. Use the original offline plan, not the narrative-only specs. Implement complete `schema.py`, `sessions.py`, `baselines.py`, `join.py`, and CLI. Group baseline by ticker + exact session slot using only `u<t` and previous 20 eligible completed trading days; require >=15 prior valid slots. Fail closed on ambiguous bar times, invalid OHLC, volume, timestamps, duplicate keys and division by zero.
2. Finish ALL daily metrics, coverage status, minute/daily volume reconciliation and B0 DIR weighted agreement; preserve missing/unavailable as NA with a status, never fabricate zeros.
3. Implement independent read-only B0 integration, finite-only feature exports, event-study controls, full deterministic synthetic demo, 20 meaningful tests, actual logs and code coverage. No `assert True` acceptance placeholders.
4. Add real CLI and human-readable instructions; return portable ZIP entries with `/` path separators, no `__pycache__` or `.pytest_cache`. Return full source, QA and logs; do not require GitHub.
5. Keep Pine third-party CC BY-NC-SA reference separate; no unreviewed direct translation. Do not claim alpha, real-data parity or G1–G3 completion.

This report records **independent code inspection plus local executable probes**, not a market-data performance assessment. The uploaded WIP code is intentionally **not** promoted into the repository's MBV engine path.
