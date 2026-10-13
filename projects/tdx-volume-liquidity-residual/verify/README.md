# VLR verification tools

**Status:** structural code and synthetic test coverage added. Python ↔ TongDaXin parity and real-world profitability are **NOT verified**.

## Setup

From this directory:

```bash
python -m pip install -r requirements.txt
python -m unittest discover -p 'test_*.py' -v
```

## Inputs

All CSVs must be chronological per ticker. OHLCV columns:
`open,high,low,close,volume`; E4 requires `amount`.
Prices and amount must use a consistent corporate-action convention.

## Baseline + challengers

`vlr.calculate(df,model='B0')` returns B0 (frozen V2.1.2).

The same interface also provides E1 (JUMBO), E2 (log-linear),
E3 (log-linear + conditional scale), and E4 (relative amount).

Output includes six states and events, 60/20/10-day frequencies,
8 mutually exclusive activity classes, XG3, XG6010 and XGLAYER.
E3 uses a longer explicit warm-up than the baseline.

## Prefix test

```bash
python prefix_invariance.py historical_ohlcva.csv --points 30
```

This checks that past values are unchanged when future bars are removed.
It does **not** show TongDaXin compatibility.

## TDX parity (required before promoting results)

Export real TongDaXin indicator outputs and align them with the exact
same bars as OHLCV. Additional columns in the aligned CSV must include
all 21 outputs listed under "Full parity is the default" below. The older
seven fields are accepted only with explicit `--scope core`.

```bash
python tdx_parity.py aligned_tdx_export.csv --initial-tr hl
python tdx_parity.py aligned_tdx_export.csv --initial-tr missing
```

Choose the initialization only after checking TongDaXin output.
The default assumes the first bar TR equals H-L, while the alternative
treats first bar TR as missing. Record which one matches. TDX software
version, data history length and STD/SMA semantics must also be recorded.

## A-share execution interface

`execution.build_execution_table` expects point-in-time historical flags
for ST, suspension, listing age and locked price limits. Missing fields raise
an error. The T+1 attempt can be FILTERED_T, UNFILLED, or
ELIGIBLE_FOR_FILL_CHECK; the last status is **not a confirmed fill**.

Historical price-limit and corporate-action data must be supplied by a
verified source. This module does not fabricate them.

## Synthetic tests

`test_synthetic.py` checks deterministic structure and T+1 lock behavior.
Synthetic tests are not evidence of excess returns or production readiness.

**Outstanding:** full point-in-time A-share study, actual TDX exports,
transaction-cost implementation, complete OOS event study.

## 2026-10-13 review corrections

`build_execution_table(bars, trading_calendar=exchange_sessions)` now requires
an explicit sorted, unique, timezone-naive exchange session calendar. Do not
substitute weekday calendars in production. Include the intended next session
and 20 sessions of history. `listing_age_days` means trading-session age.
Suspension records should be supplied explicitly (including actual daily amount).
Missing bars are not automatically interpreted as suspensions or zero turnover.

Only boolean or numeric 0/1 flags are accepted; missing values and strings such
as `"False"` fail validation. The same ticker/date cannot occur twice.
`DATA_MISSING` identifies an absent intended T+1 bar, `PENDING` an unknown next
calendar session, and `UNFILLED` a supplied suspended/locked next session.
These are distinct from `ELIGIBLE_FOR_FILL_CHECK`, which still does not prove a fill.
Missing history prevents a 20-session turnover average from bridging gaps.

Parity requires a date column and compares every bar after the baseline's
145-bar warm-up using one common set. All outputs required by the selected scope must be finite;
event exports must be exactly 0/1. Empty comparisons fail. Pre-warm-up outputs
are excluded. Replica-generated exports in tests verify gate behavior only,
not authentic TongDaXin parity. Date order, uniqueness, one-ticker identity
(when supplied), finite nonnegative inputs, positive prices and OHLC bounds
are checked by `calculate`. Array-only callers without a date column remain
responsible for chronology; CSV callers should always supply dates.

## Accepted recommendations: second revision

### Full parity is the default

`python tdx_parity.py aligned_tdx_export.csv` now requires 21 outputs:
Z/RVRAW/DIR/RHO; EU/VU/ABU/ED/VD/ABD; XG3/XG6010/XGLAYER;
QUIET/WARMUP/ACTIVE/HIGHACT/LONGACT/HOT/FADING/OTHER. Each CSV column
uses the `TDX_` prefix. `--scope core` explicitly selects the old seven-series
diagnostic only; core success is not full project acceptance.

Import `tdx_full_export.tdx` as a separate diagnostic indicator and export its
outputs on the same bars, in the same order, as OHLCV. This file derives from
the frozen B0 calculation and existing selector definitions; it does not replace
the stable indicator. Its compilation on a real TDX installation remains pending.
Record software version, exact commit, ticker, price/volume adjustment convention,
history start/end and exported-file hash beside results. Check edge fixtures:
initialization, zero volume, flat bars, threshold equality, cooldown sequences,
price limits and corporate actions. Python fixture exports are not TDX evidence.

### Calendar-block inference

```python
from inference import block_bootstrap
# events has date and return; return can be matched-control excess return.
report = block_bootstrap(events, trading_calendar=evaluation_sessions,
                         block_lengths=(5, 10, 20), repetitions=2000, seed=20261013)
```

The estimand is the event-weighted mean, not an equal-date portfolio mean.
Contiguous calendar blocks retain each day's entire cross-section. Sessions
without events stay on the supplied, predeclared evaluation calendar. The
percentile interval and counts are reported separately for every block length.
At least two blocks must fit. Missing returns fail; >5% empty-event draws fail.
The remaining empty draws are disclosed. This is a moving-block approximation,
not proof of significance; inspect sample size and sensitivity to block length.
Do not remove missing/censored outcomes merely to obtain a passing input.

### Open-price event simulation with explicit assumptions

```python
from trade_study import simulate_events
trades = simulate_events(bars, trading_calendar=exchange_sessions,
    holding_sessions=5, buy_cost_bps=10, sell_cost_bps=20, slippage_bps=5,
    price_convention="describe the actual consistent adjustment method here")
```

Numbers above are examples, not current fee recommendations. In addition to
execution-table columns, require positive `open` and historical boolean
`open_buyable`/`open_sellable` from a verified opening-auction source. Daily
high/low or end-of-day locked flags cannot establish opening executability.
Same-side slippage applies adversely at both ends; buy and sell costs apply
to their respective traded notionals. The net return is sale proceeds divided
by acquisition outlay minus one. The price convention must account consistently
for corporate actions; the module does not calculate adjustments or dividends.

Each signal is an independent event. Entry is T+1 open; a holding horizon h
exits no earlier than entry+h exchange sessions. Blocked exits defer; an absent
holding-period bar becomes EXIT_DATA_MISSING, an unfinished horizon becomes
OPEN_CENSORED. Neither receives a zero or fabricated realized return.
Summaries must report every status and explain unresolved outcomes before
inference. These overlapping events are not a portfolio equity curve.

Not implemented: queue position, partial fills, capital allocation, lot sizes,
minimum commissions, market impact or point-in-time fee schedules. Supply
assumptions externally or extend the simulator before capacity/profitability claims.

### Prospective confirmation registration

`python confirmation.py study_spec.json registration.json` writes a new file
exclusively and refuses to overwrite one. Required spec fields are listed in
`confirmation.REQUIRED`: exact code commit, data source/version, universe,
price convention, parameters, costs, prior exposure, confirmation dates,
primary metric, acceptance rule, block lengths and outcomes_previously_viewed.
All fields must be populated. The last field must be boolean false, and the
confirmation start must be a future UTC date. The result records UTC registration
time and a SHA-256 of the canonical specification; commit it before collecting
or examining the confirmation sample. This hash detects spec changes when
compared to the committed version; it is not proof of ignorance or tamperproof storage.
No real sample has been registered or evaluated by this change. Never relabel
2021–2026 data as untouched. Choose a feasible new window before registration.
