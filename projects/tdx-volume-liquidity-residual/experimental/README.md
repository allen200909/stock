# V2.2 Experimental Challengers

> Branch: `v2.2-experimental`

This branch contains challenger models only. None of them is a stable replacement for V2.1.2 until the validation protocol is completed.

## Experiment matrix

| ID | Model | Purpose |
|---|---|---|
| E1 | Linear + JUMBO regime | isolate RVRAW>RVCAP instead of forcing giant-volume bars into ordinary Z logic |
| E2 | Log-linear residual | reduce right-skew and multiplicative scale effects |
| E3 | Log-linear + conditional scale | address residual heteroskedasticity across RVOL regimes |
| E4 | AMOUNT-based activity | test whether turnover amount is more robust than raw share volume around corporate actions |

## Promotion rule

A challenger can replace V2.1.2 only if it wins on the same sample and execution assumptions in:

- OOS discrimination;
- stability across years and market regimes;
- transaction-cost resilience;
- robustness to RVOL buckets;
- interpretability.

A more Gaussian Z distribution alone is not sufficient.

## Important

All formulas here are **experimental drafts** and must be compiled in TongDaXin and matched against Python before performance conclusions are accepted.
