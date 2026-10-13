# Review Response — 2026-10-13

This document records how the external optimization review was incorporated.

## Accepted immediately

### A. Freeze V2.1.2 as baseline

The review identified material statistical and execution issues. Rather than rewrite the historical baseline in place, V2.1.2 is frozen for reproducible comparison.

### B. Documentation correction

The documentation now states accurately that:

- training values use fixed upper clipping;
- EXPECT uses clipped RVFIT;
- current MOV and threshold logic use raw values;
- the giant-volume region is a known risk area.

### C. Validation protocol

Added `validation-protocol.md` with:

- TDX/Python parity gate;
- universe and corporate-action requirements;
- T+1 execution;
- RVOL-matched controls;
- OOS split;
- walk-forward;
- sensitivity analysis;
- challenger promotion rules.

### D. A-share execution layer

Added `a-share-execution-layer.md`. Raw factor events remain separate from tradability filters.

### E. Activity-state coverage

Added:

- FADING
- OTHER

The default selector remains ACTIVE OR HIGHACT.

## Accepted as experimental challengers

The review's strongest statistical finding is heteroskedastic residuals across RVOL regimes and the special behavior of RVRAW>RVCAP.

These changes are therefore isolated on `v2.2-experimental`:

- E1: JUMBO regime;
- E2: log-linear residual;
- E3: log-linear + conditional scale;
- E4: amount-based activity measure.

None is promoted solely because its standardized residual is more distributionally uniform.

## Deferred

### Asymmetric Z thresholds

Potentially useful, but it is premature to add ZUP/ZDN before testing whether the conditional-scale variants reduce the skew.

### Heavy multiple-testing corrections

Methods such as White's Reality Check or Deflated Sharpe may be added after the event-study pipeline is stable. The immediate priority is parity, data integrity, OOS separation, and controlled baselines.

### Runtime cross-formula references

Instead of making TDX selectors depend on named indicator outputs, the preferred engineering direction is a single source/template that generates standalone TDX formulas. This avoids local formula-name dependencies.

