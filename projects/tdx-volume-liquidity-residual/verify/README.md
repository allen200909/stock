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
`TDX_Z,TDX_RVRAW,TDX_DIR,TDX_RHO,TDX_EU,TDX_VU,TDX_ABU`.

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
