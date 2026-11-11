# MBV V0.1 — Carbon R3 Independent QA (2026-11-11)

**Decision: G0 FAIL / NOT ACCEPTED.** The R3 archive contains meaningful local improvements to the isolated rolling baseline and join uniqueness, but the production code path still contains legacy all-sample baselines and cannot connect the new baseline output to burst detection. Do not merge to `master`, do not present a valid MBV research factor, and do not claim real-world alpha.

## Source and testing evidence

- Archive: `MBV_V0.1_Carbon_Completed_R3.zip`.
- ZIP SHA256: `8609bfb66a85a5070692f6c29f759ee99305953c7e5a6e28bdda2b9cf13b92ba`.
- 27 ZIP entries, **24 containing Windows backslash separators**. The archive also includes stale `__pycache__` files and no actual pytest execution logs. It needs normalized portable paths and clean packaging.
- Independent environment: Linux / Python 3.13.5 / pytest / pandas / NumPy.
- From normalized extract root: `python -m pytest -q tests -ra` => **4 passed**.
- `python -m pytest --cov=mbv --cov-report=term-missing -q tests` => **4 passed; 51% total statement coverage** (61 statements, 30 not covered); `aggregate.py` **0%**.
- Test collection: `tests/test_features.py::test_t01_no_future_leakage`, `test_t07_invalid_ohlc`; `tests/test_robustness.py::test_t01_no_future_leakage`, `test_t14_duplicate_key_join`.
- The **first** T01 test is still `assert True` and has no real connection to the rolling algorithm. One legitimate limited T01 test exists in `test_robustness.py`, but does not validate the full dataflow.

## Positives — independently verified

1. **Isolated baseline causality**: `mbv.baselines.compute_rolling_tod_baseline` groups by `symbol` + `time_slot`, uses `shift(1)`, and produces unchanged historical baselines when a later day is appended in a controlled valid fixture. Different securities have separate baselines in the controlled fixture.
2. **Minimum raw observation count**: for 13 prior sample rows, baseline remains NaN in a simple constant-volume fixture. (However zero volume rows are incorrectly counted as eligible; see defects.)
3. **Join duplication guard**: `mbv.join.join_daily_vlr_mbv` rejects repeated `(symbol,trade_date)` keys, retains B0 rows when valid MBV input is missing, and inserts `MISSING_MINUTE_DATA` when the MBV table contains the required status column.
4. **Body efficiency**: `detect_bursts` still uses body-to-range efficiency as well as relative volume to qualify directional bursts.
5. **Frozen references**: R3's included `vlr.py`, `validation.py`, `inference.py`, third-party NOTICE and Pine reference hashes match the values recorded in `reports/ENVIRONMENT.md`. This only demonstrates equality to the archived reference hashes; no authentic TDX parity or full repository-diff comparison was performed.

## Reproduced blocking defects

### P0 — incompatible and leaky baseline pathway

- `mbv.adapters.build_tod_baseline` **still uses** `df.groupby(df['ts'].dt.time)['volume'].median()` on the entire supplied sample (all symbols/all dates). Example one ticker 09:30 volume=100, append next-day volume=10000: returned baseline changes from **100 to 5050**. Combining another ticker at the same slot also returns **5050**. Its `lookback_days` argument is unused.
- The new `compute_rolling_tod_baseline` outputs a **DataFrame** containing `symbol,trade_date,time_slot,volume,baseline`; `mbv.features.detect_bursts` still expects a **Series indexed by time** and maps by `ts.dt.time` only. Passing the actual rolling baseline DataFrame directly causes **`ValueError: 2`** in pandas. There is no complete tested path from historical data to correct per-row baseline to burst detection. Even passing a global Series would reintroduce cross-ticker/date contamination.
- New rolling baseline counts zero-volume historical entries toward `min_history_days`. In a 21-day synthetic fixture with 15 zeros then 6 positive days, day 21 returns baseline **0.0**, whereas only five positive historical days should require `INSUFFICIENT_HISTORY`/NaN. It also silently sums duplicate (ticker, date, slot) records instead of rejecting them.

### P0 — unvalidated data and invalid signal states

- `validate_minute_bars` still accepts negative or NaN volume, duplicate `(symbol,ts)`, **08:00** non-session bar, and `bar_end` semantics at `09:30` without conversion or rejection. `semantics` is ignored; timezone, frequency, valid slot sets, numeric finite checks, and `lot_100` units are unimplemented.
- A zero baseline combined with positive volume produces `rel_vol=inf` and `is_burst=True`; there is no `BASELINE_INVALID` guard or finite output contract.
- `aggregate_daily_features` emits zero `burst_count` / `burst_share` on `NO_VOLUME`, conflating missing/unusable data with a valid zero-burst day. It does not enforce 95% slot coverage.
- The join expects `mbv_features['feature_status']` to exist. For valid-keys MBV input lacking this column, it raises **`KeyError('feature_status')`**, not a controlled data-contract error. Null join keys are not explicitly rejected.

### P1 — mandatory V0.1 features and reproducibility absent

- `aggregate.py` implements only `burst_count`, `burst_share`, `feature_status`, not peak ratio, dominance, concentration, single-burst case, direction agreement, slot coverage or minute/daily volume reconciliation.
- No `mbv/schema.py`, `mbv/sessions.py`, CLI, historical CSV/Parquet adapter, read-only B0 integration, event-study matching/negative controls, calendar gate, bootstrap wrapper, synthetic demo runner or end-to-end report.
- `config/default.yaml`, `SPEC.md`, `DATA_CONTRACT.md` and `THREAT_MODEL.md` describe designs, but the corresponding controls and outputs are not present in executable code. `reports/ENVIRONMENT.md` mentions CSV/Parquet support although there is no such adapter in the shipped `mbv/` code.

## Original acceptance matrix

| ID | Status | Evidence |
|---|---|---|
| T01 | PARTIAL / FAIL END-TO-END | Standalone causal median improvement; original adapter still looks ahead; placeholder `assert True` remains |
| T02 | PARTIAL / FAIL END-TO-END | Standalone historical prefix stable in a controlled fixture; no integrated signal prefix test |
| T03 | PARTIAL / FAIL END-TO-END | New median splits symbols; legacy adapter and feature mapper do not |
| T04 | FAIL | 08:00 and other invalid sessions can pass |
| T05 | FAIL | `semantics` ignored, no bar_start/end normalization |
| T06 | NOT IMPLEMENTED | No 1m/5m slot, count and coverage validation |
| T07 | FAIL | Negative/NaN volumes, duplicates, zero baseline unguarded |
| T08 | FAIL | No coverage gate; unavailable features written as zeros |
| T09 | PARTIAL / FAIL | Raw historical count gate exists; positive-history eligibility and statuses missing |
| T10 | NOT IMPLEMENTED | Daily directional/HHI metrics absent |
| T11 | NOT IMPLEMENTED | No concentrated-vs-uniform fixture |
| T12 | PARTIAL | Missing MBV one-to-one left join handled only if status schema exists |
| T13 | NOT IMPLEMENTED | Point-in-time risk flags absent |
| T14 | PARTIAL | Day-key duplicates rejected; minute-key duplicates / null keys not covered |
| T15 | NOT IMPLEMENTED | No B0 read-only bridge or parity regression |
| T16 | NOT IMPLEMENTED | No calendar-guarded event study |
| T17 | NOT IMPLEMENTED | No future outcome isolation |
| T18 | NOT IMPLEMENTED | No matched controls / insufficient-sample outcomes |
| T19 | NOT IMPLEMENTED | No block bootstrap integration |
| T20 | NOT IMPLEMENTED | No reproducible CLI `SYNTHETIC_DEMO` |

**No T01–T20 case has the full requested pass evidence; four passing micro-tests are not complete acceptance.**

## Gate determination

- **G0: FAILED.** Incompatible baseline APIs, legacy look-ahead and invalid-data acceptance persist.
- **G1: BLOCKED_REAL_DATA.** No verified QMT/PTADE A-share minute data or volume reconciliation.
- **G2: NOT VERIFIED.** Authentic TDX full 21-series parity remains pending in parent baseline project.
- **G3: NOT TESTED.** No true OOS matched-control event research.

## Specific Carbon instructions for next iteration — fix the critical path before expanding features

1. **One canonical baseline API:** remove/disable the legacy all-sample adapter or route every user-facing call through a tested past-only function. Define a unique key of `(symbol, trade_date, time_slot)` and return an aligned row-level DataFrame or MultiIndex Series. Never map only by clock time. Use only completed trading dates `u<t`; 20 valid prior session slots, at least 15 positive-volume observations; no zero/NaN/duplicate records counted.
2. **Fail-closed session and input contract:** implement strict 1m/5m time slots for both sessions in Asia/Shanghai, explicit bar_start vs bar_end handling, and symbolic bounds/uniqueness/finite OHLCV/volume unit validation. Test 08:00, 11:30, 12:00, 15:00 boundaries and closing-auction handling.
3. **Integrated burst engine:** join baseline by full key, reject zero or unavailable baseline with NaN ratio plus status (never inf), apply both `rel_vol >=2.5` and `abs(E)>=0.10`, and assert valid signal values and no cross-asset contamination using full-sample and prefix-truncated data.
4. **Quality-gated aggregation and B0 left join:** compute all specified outputs; distinguish genuine zero events from missing history/low coverage/no volume; enforce unique nonnull keys and deterministic status precedence. Implement 95% slot coverage and source-unit reconciliation.
5. Replace placeholder tests. First pass meaningful **T01–T09, T12, T14** tests for this critical path, then implement **T10–T11, T13, T15–T20** and a CLI with self-contained synthetic example. Run the real commands and save logs; no simulated PASS or claims about unavailable data.
6. Deliver a portable ZIP with slash-separated entry names, no `__pycache__`, and actual Python source, tests, executable setup instructions and evidence. GitHub clone/push is not required in Carbon's offline environment.

For a valid R4, provide the raw pytest output, coverage and a reproducible single command. Do not modify VLR frozen B0 or imply investment advice or verified edge.