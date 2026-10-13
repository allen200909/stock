# Validation Protocol — VLR V2.1.2 Baseline

## 1. Purpose

This protocol is frozen before full-scale performance testing. Its purpose is to prevent silent parameter drift and post-hoc tuning.

Baseline under test: **V2.1.2**

Primary research question:

> Does the residual signal add information beyond simple volume expansion after controlling for date and RVOL?

## 2. Parity gate

No event study is considered valid until the Python implementation is matched against TongDaXin outputs bar-by-bar.

Required exported TDX series:

- Z
- EU
- VU
- ABU
- RVRAW
- DIR
- RHO

Acceptance target:

- numeric series: max absolute difference <= 1e-6 where definitions are identical;
- boolean signals: 100% exact match after warm-up.

If parity fails, fix the Python replica before any performance conclusion is used.

## 3. Data universe

Preferred production study:

- all A-shares with point-in-time membership;
- include delisted securities;
- preserve historical board/ST status where available;
- use an exchange trading calendar;
- retain at least 300 bars of warm-up history before the first evaluated date.

Do not use only today's surviving stock list for final conclusions.

## 4. Corporate actions and price convention

Research output must state:

- raw / forward-adjusted / backward-adjusted / total-return convention;
- how ex-rights and ex-dividend dates are handled;
- whether volume/amount series are adjusted.

Forward returns must use a return-consistent adjustment method. Large corporate-action jumps must not be interpreted as price-impact signals.

## 5. Signal timing and execution

- Signal is confirmed at T close.
- Earliest strategy action is T+1.
- If T+1 intended entry is not executable because of price-limit constraints, record **UNFILLED** rather than assume a fill.
- Exit on locked limit-down days is deferred until executable.
- Intraday provisional signals are not part of this baseline test.

## 6. Execution filters

Raw factor events and executable trade candidates are stored separately.

Suggested executable-universe filters are defined in `a-share-execution-layer.md`.

## 7. Event windows

Evaluate forward horizons:

- 1 trading day
- 3 trading days
- 5 trading days
- 10 trading days
- 20 trading days

Record:

- mean return
- median return
- win rate
- standard deviation
- MFE
- MAE
- event count
- executable event count
- unfilled count

## 8. Controls

At minimum compare each EU event against:

1. unconditional same-date universe;
2. same-date securities in a similar RVOL bucket;
3. preferably similar market-cap or industry group where point-in-time fields are available.

The key test is whether residual-based selection adds information after controlling for simple volume expansion.

## 9. Dependence and uncertainty

Signals on the same trading day are cross-sectionally correlated.

Preferred inference:

- bootstrap by trading date; or
- standard errors clustered by date.

Do not report naive per-event t-statistics as if events were independent.

## 10. Train / OOS split

Initial fixed split:

- Train / research: 2015-01-01 through 2020-12-31
- Sealed OOS: 2021-01-01 through 2026-09-30

Parameters may only be changed using the training segment before opening OOS results.

Secondary robustness:

- rolling 3-year train / 1-year test walk-forward.

## 11. Parameter sensitivity

Only scan a limited core set initially:

- N
- ZTH
- RVVAC
- COOL

Report all attempted combinations, not only the best one.

Prefer broad stable performance plateaus over isolated optima.

## 12. Baseline vs challenger

Compare on identical samples and execution assumptions:

- B0: V2.1.2 Linear baseline
- E1: Linear + JUMBO regime
- E2: Log-linear residual
- E3: Log-linear + conditional scale
- E4: Amount-based activity variant

A challenger may replace the baseline only if it improves:

1. OOS discrimination;
2. robustness across years/regimes;
3. transaction-cost resilience;
4. statistical stability;
5. interpretability.

A more Gaussian Z distribution alone is not sufficient.

## 13. Reporting rule

Every result table must include:

- exact code commit;
- data source/version;
- universe construction;
- date range;
- parameter set;
- cost assumptions;
- sample count;
- whether result is train, validation, or OOS.

