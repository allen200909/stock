# Python Verification

The files in this directory are research-side replicas of the frozen V2.1.2 baseline.

They are not authoritative until matched bar-by-bar against TongDaXin exports.

## Required workflow

1. Export TDX series for representative securities.
2. Run the Python replica on identical OHLCV history.
3. Compare Z, RVRAW, DIR, RHO and event booleans.
4. Resolve differences in SMA, STD, warm-up and missing-value semantics.
5. Only after parity is reached should the event-study pipeline be used.

Acceptance target:

- numeric series: maximum absolute difference <= 1e-6 where definitions are identical;
- boolean signals: 100% exact match after warm-up.

Planned files:

- `vlr.py` — V2.1.2 baseline calculation
- `prefix_invariance.py` — no-future-data prefix test
- later: event-study and OOS evaluation scripts
