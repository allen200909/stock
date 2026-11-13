# MBV V0.1 Event Study Report (`SYNTHETIC_DEMO`)

> **STUDY LABEL: `SYNTHETIC_DEMO`** | Research Grade: `SYNTHETIC_DEMO_ONLY` | VLR Parity: `TDX_PARITY_NOT_VERIFIED`
> **WARNING**: Intraday OHLCV body efficiency is a structural proxy ONLY — NOT order-flow or active buy/sell volume. Do NOT interpret synthetic or unverified outputs as alpha or live trading signals.
> **CONCLUSION**: NO_RESEARCH_CONCLUSION: SYNTHETIC_DEMO output only exercises the code path; it is not evidence of MBV incremental value or alpha.

## 0. Gates
- `G1_REAL_MINUTE_DATA`: `BLOCKED_REAL_DATA`
- `G2_TDX_B0_PARITY`: `NOT_VERIFIED`
- `G3_REAL_EVENT_STUDY`: `NOT_TESTED`

## 0b. Study Context (calendar / pre-registration)
- **Study Context**: `{'study_mode': 'SYNTHETIC_DEMO', 'research_grade': 'SYNTHETIC_DEMO_ONLY', 'calendar_kind': 'SYNTHETIC_GENERATED', 'calendar_sha256': '76b5b1daa2118ab330c0aa670226091b5dd3bb7cabc0ad7c07e6c309fb9355dd', 'calendar_source': 'mbv.adapters.generate_synthetic_market_bundle(seed=20261111, n_sessions=170)', 'calendar_sessions': 170}`

## 1. Sample Coverage & Attrition
- **Evaluation Calendar Sessions**: `170`
- **Total Daily Panel Rows**: `510`
- **MBV `feature_status` Counts**: `{'MISSING_MINUTE_DATA': 375, 'OK': 90, 'INSUFFICIENT_HISTORY': 45}`
- **T+1 `fill_status` Counts**: `{'TRADABILITY_UNVERIFIED_T1': 507, 'PENDING_FUTURE_SESSION': 3}`
- **T+1 `execution_class` Counts**: `{'FILL_UNVERIFIED': 507, 'NO_DATA': 3}`
- **Return basis**: `fwd_ret_*` / `mean_return` are HYPOTHETICAL T+1 open-price returns (factor research) and are NOT fill returns. `exec_*` statistics include only CONFIRMED_FILLED (order evidence) and STATUS_CHECKED_EXECUTABLE rows; FILL_UNVERIFIED rows (incl. OPEN_LIMIT_UP_FILL_UNVERIFIED_T1) are excluded.

## 2. Matched & Permutation Controls (Groups D & E)
- **H1 Matched Control (Same-Date + RVOL Bucket + board policy)**: `{'board_policy': 'strict', 'board_constraint': 'SAME_BOARD', 'seed': 20261111, 'outcome_col': 'fwd_ret_5d', 'n_relaxed_board': 0, 'unmatched_reasons': {'NO_CANDIDATE': 5}, 'status': 'INCONCLUSIVE', 'reason': 'INSUFFICIENT_MATCHED_CONTROLS', 'n_treated': 5, 'n_matched': 0, 'unmatched_rate': 1.0, 'mean_treated': nan, 'mean_control': nan, 'mean_excess': nan}`
- **H2 Matched Control (Same-Date + RVOL Bucket + board policy)**: `{'board_policy': 'strict', 'board_constraint': 'SAME_BOARD', 'seed': 20261111, 'outcome_col': 'mae_5d', 'n_relaxed_board': 0, 'unmatched_reasons': {'NO_CANDIDATE': 1}, 'status': 'INCONCLUSIVE', 'reason': 'INSUFFICIENT_MATCHED_CONTROLS', 'n_treated': 1, 'n_matched': 0, 'unmatched_rate': 1.0, 'mean_treated': nan, 'mean_control': nan, 'mean_excess': nan}`
- **Group E Within-RVOL-Bucket Permutation Negative Control**: `{'method': 'WITHIN_RVOL_BUCKET_PERMUTATION', 'seed': 20261111, 'n_permutations_requested': 1000, 'n_permutations_valid': 1000, 'rvol_buckets': [0.0, 1.2, 1.5, 2.2, 3.0, 100.0], 'bucket_counts': {2: 3, 3: 3}, 'n_rvol_missing': 0, 'observed_spread': 0.05542573824316075, 'permuted_mean_spread': 0.021064378849501984, 'p_value_two_sided': 0.3386613386613387, 'n_permutable_buckets': 1, 'status': 'COMPLETED', 'reason': 'COMPLETED_WITHIN_BUCKET', 'n_events': 6, 'interpretation': 'NOT_EVIDENCE_SYNTHETIC'}`

## 3. Calendar-Block Bootstrap (`reference/vlr_verify/inference.py`)
- **Bootstrap Status**: `OK` 
- **Bootstrap Settings / Attrition**: `{'target_group': 'B_MBV_BULL_BURST_ONLY', 'outcome_col': 'fwd_ret_5d', 'seed': 20261013, 'repetitions': 500, 'confidence': 0.95, 'evaluation_sessions': 45, 'evaluation_window': ['2025-08-05', '2025-10-07'], 'block_lengths_requested': [5, 10, 20], 'block_lengths_used': [5, 10, 20], 'block_lengths_dropped_too_long': [], 'raw_events': 9, 'events_used': 7, 'events_dropped_missing_return': 2}`

```text
 block_length     mean   ci_low  ci_high  events  sessions  valid_draws  empty_draws  repetitions     seed  confidence
            5 0.063517 0.054156 0.073075       7        45          499            1          500 20261013        0.95
           10 0.063517 0.057640 0.072517       7        45          495            5          500 20261013        0.95
           20 0.063517 0.058300 0.072258       7        45          488           12          500 20261013        0.95
```

## 4. Group × Horizon Summary

```text
    study_mode                   group  horizon_days  raw_events               return_basis  effective_events  dropped_missing_return  mean_return  median_return  win_rate  mean_mfe  mean_mae  fill_unverified_events  exec_effective_events  exec_mean_return group_status
SYNTHETIC_DEMO           A_VLR_EU_ONLY             1           8 HYPOTHETICAL_T1_OPEN_PRICE                 8                       0    -0.000562      -0.003337  0.375000  0.010988 -0.008493                       8                      0               NaN           OK
SYNTHETIC_DEMO           A_VLR_EU_ONLY             3           8 HYPOTHETICAL_T1_OPEN_PRICE                 7                       1     0.036037       0.039555  0.857143  0.050548 -0.011729                       8                      0               NaN           OK
SYNTHETIC_DEMO           A_VLR_EU_ONLY             5           8 HYPOTHETICAL_T1_OPEN_PRICE                 6                       2     0.047025       0.048637  1.000000  0.063656 -0.009613                       8                      0               NaN           OK
SYNTHETIC_DEMO           A_VLR_EU_ONLY            10           8 HYPOTHETICAL_T1_OPEN_PRICE                 5                       3     0.184654       0.170717  1.000000  0.195847 -0.010442                       8                      0               NaN           OK
SYNTHETIC_DEMO           A_VLR_EU_ONLY            20           8 HYPOTHETICAL_T1_OPEN_PRICE                 2                       6     0.435663       0.435663  1.000000  0.449113 -0.013312                       8                      0               NaN INCONCLUSIVE
SYNTHETIC_DEMO          A_VLR_ABU_ONLY             1           1 HYPOTHETICAL_T1_OPEN_PRICE                 1                       0     0.019922       0.019922  1.000000  0.026725 -0.001458                       1                      0               NaN INCONCLUSIVE
SYNTHETIC_DEMO          A_VLR_ABU_ONLY             3           1 HYPOTHETICAL_T1_OPEN_PRICE                 1                       0     0.082362       0.082362  1.000000  0.091108 -0.001458                       1                      0               NaN INCONCLUSIVE
SYNTHETIC_DEMO          A_VLR_ABU_ONLY             5           1 HYPOTHETICAL_T1_OPEN_PRICE                 1                       0     0.179786       0.179786  1.000000  0.181487 -0.001458                       1                      0               NaN INCONCLUSIVE
SYNTHETIC_DEMO          A_VLR_ABU_ONLY            10           1 HYPOTHETICAL_T1_OPEN_PRICE                 1                       0     0.232507       0.232507  1.000000  0.250000 -0.001458                       1                      0               NaN INCONCLUSIVE
SYNTHETIC_DEMO          A_VLR_ABU_ONLY            20           1 HYPOTHETICAL_T1_OPEN_PRICE                 0                       1          NaN            NaN       NaN       NaN       NaN                       1                      0               NaN INCONCLUSIVE
SYNTHETIC_DEMO           A_VLR_VU_ONLY             1           1 HYPOTHETICAL_T1_OPEN_PRICE                 1                       0     0.000674       0.000674  1.000000  0.008760 -0.005166                       1                      0               NaN INCONCLUSIVE
SYNTHETIC_DEMO           A_VLR_VU_ONLY             3           1 HYPOTHETICAL_T1_OPEN_PRICE                 1                       0     0.090746       0.090746  1.000000  0.092318 -0.005166                       1                      0               NaN INCONCLUSIVE
SYNTHETIC_DEMO           A_VLR_VU_ONLY             5           1 HYPOTHETICAL_T1_OPEN_PRICE                 1                       0     0.113432       0.113432  1.000000  0.114331 -0.005166                       1                      0               NaN INCONCLUSIVE
SYNTHETIC_DEMO           A_VLR_VU_ONLY            10           1 HYPOTHETICAL_T1_OPEN_PRICE                 1                       0     0.159479       0.159479  1.000000  0.172507 -0.005166                       1                      0               NaN INCONCLUSIVE
SYNTHETIC_DEMO           A_VLR_VU_ONLY            20           1 HYPOTHETICAL_T1_OPEN_PRICE                 0                       1          NaN            NaN       NaN       NaN       NaN                       1                      0               NaN INCONCLUSIVE
SYNTHETIC_DEMO   B_MBV_BULL_BURST_ONLY             1           9 HYPOTHETICAL_T1_OPEN_PRICE                 9                       0    -0.004828      -0.004129  0.222222  0.008706 -0.011433                       9                      0               NaN           OK
SYNTHETIC_DEMO   B_MBV_BULL_BURST_ONLY             3           9 HYPOTHETICAL_T1_OPEN_PRICE                 8                       1     0.040213       0.036116  1.000000  0.048675 -0.012603                       9                      0               NaN           OK
SYNTHETIC_DEMO   B_MBV_BULL_BURST_ONLY             5           9 HYPOTHETICAL_T1_OPEN_PRICE                 7                       2     0.063517       0.052587  1.000000  0.075686 -0.010914                       9                      0               NaN           OK
SYNTHETIC_DEMO   B_MBV_BULL_BURST_ONLY            10           9 HYPOTHETICAL_T1_OPEN_PRICE                 5                       4     0.200251       0.210145  1.000000  0.213404 -0.009410                       9                      0               NaN           OK
SYNTHETIC_DEMO   B_MBV_BULL_BURST_ONLY            20           9 HYPOTHETICAL_T1_OPEN_PRICE                 1                       8     0.511226       0.511226  1.000000  0.513032 -0.006968                       9                      0               NaN INCONCLUSIVE
SYNTHETIC_DEMO   C_H1_EU_HIGH_BULL_MBV             1           7 HYPOTHETICAL_T1_OPEN_PRICE                 7                       0    -0.001478      -0.003997  0.285714  0.010825 -0.009288                       7                      0               NaN           OK
SYNTHETIC_DEMO   C_H1_EU_HIGH_BULL_MBV             3           7 HYPOTHETICAL_T1_OPEN_PRICE                 6                       1     0.045041       0.045187  1.000000  0.055069 -0.010407                       7                      0               NaN           OK
SYNTHETIC_DEMO   C_H1_EU_HIGH_BULL_MBV             5           7 HYPOTHETICAL_T1_OPEN_PRICE                 5                       2     0.056262       0.052587  1.000000  0.071703 -0.007605                       7                      0               NaN           OK
SYNTHETIC_DEMO   C_H1_EU_HIGH_BULL_MBV            10           7 HYPOTHETICAL_T1_OPEN_PRICE                 4                       3     0.197777       0.196326  1.000000  0.210096 -0.008139                       7                      0               NaN INCONCLUSIVE
SYNTHETIC_DEMO   C_H1_EU_HIGH_BULL_MBV            20           7 HYPOTHETICAL_T1_OPEN_PRICE                 1                       6     0.511226       0.511226  1.000000  0.513032 -0.006968                       7                      0               NaN INCONCLUSIVE
SYNTHETIC_DEMO C_H1_EU_LOW_OR_WEAK_MBV             1           1 HYPOTHETICAL_T1_OPEN_PRICE                 1                       0     0.005855       0.005855  1.000000  0.012129 -0.002928                       1                      0               NaN INCONCLUSIVE
SYNTHETIC_DEMO C_H1_EU_LOW_OR_WEAK_MBV             3           1 HYPOTHETICAL_T1_OPEN_PRICE                 1                       0    -0.017984      -0.017984  0.000000  0.023421 -0.019657                       1                      0               NaN INCONCLUSIVE
SYNTHETIC_DEMO C_H1_EU_LOW_OR_WEAK_MBV             5           1 HYPOTHETICAL_T1_OPEN_PRICE                 1                       0     0.000836       0.000836  1.000000  0.023421 -0.019657                       1                      0               NaN INCONCLUSIVE
SYNTHETIC_DEMO C_H1_EU_LOW_OR_WEAK_MBV            10           1 HYPOTHETICAL_T1_OPEN_PRICE                 1                       0     0.132162       0.132162  1.000000  0.138854 -0.019657                       1                      0               NaN INCONCLUSIVE
SYNTHETIC_DEMO C_H1_EU_LOW_OR_WEAK_MBV            20           1 HYPOTHETICAL_T1_OPEN_PRICE                 1                       0     0.360100       0.360100  1.000000  0.385194 -0.019657                       1                      0               NaN INCONCLUSIVE
SYNTHETIC_DEMO C_H2_ABU_OFFSETTING_MBV             1           1 HYPOTHETICAL_T1_OPEN_PRICE                 1                       0     0.019922       0.019922  1.000000  0.026725 -0.001458                       1                      0               NaN INCONCLUSIVE
SYNTHETIC_DEMO C_H2_ABU_OFFSETTING_MBV             3           1 HYPOTHETICAL_T1_OPEN_PRICE                 1                       0     0.082362       0.082362  1.000000  0.091108 -0.001458                       1                      0               NaN INCONCLUSIVE
SYNTHETIC_DEMO C_H2_ABU_OFFSETTING_MBV             5           1 HYPOTHETICAL_T1_OPEN_PRICE                 1                       0     0.179786       0.179786  1.000000  0.181487 -0.001458                       1                      0               NaN INCONCLUSIVE
SYNTHETIC_DEMO C_H2_ABU_OFFSETTING_MBV            10           1 HYPOTHETICAL_T1_OPEN_PRICE                 1                       0     0.232507       0.232507  1.000000  0.250000 -0.001458                       1                      0               NaN INCONCLUSIVE
SYNTHETIC_DEMO C_H2_ABU_OFFSETTING_MBV            20           1 HYPOTHETICAL_T1_OPEN_PRICE                 0                       1          NaN            NaN       NaN       NaN       NaN                       1                      0               NaN INCONCLUSIVE
SYNTHETIC_DEMO        C_H3_VU_NO_BURST             1           0 HYPOTHETICAL_T1_OPEN_PRICE                 0                       0          NaN            NaN       NaN       NaN       NaN                       0                      0               NaN INCONCLUSIVE
SYNTHETIC_DEMO        C_H3_VU_NO_BURST             3           0 HYPOTHETICAL_T1_OPEN_PRICE                 0                       0          NaN            NaN       NaN       NaN       NaN                       0                      0               NaN INCONCLUSIVE
SYNTHETIC_DEMO        C_H3_VU_NO_BURST             5           0 HYPOTHETICAL_T1_OPEN_PRICE                 0                       0          NaN            NaN       NaN       NaN       NaN                       0                      0               NaN INCONCLUSIVE
SYNTHETIC_DEMO        C_H3_VU_NO_BURST            10           0 HYPOTHETICAL_T1_OPEN_PRICE                 0                       0          NaN            NaN       NaN       NaN       NaN                       0                      0               NaN INCONCLUSIVE
SYNTHETIC_DEMO        C_H3_VU_NO_BURST            20           0 HYPOTHETICAL_T1_OPEN_PRICE                 0                       0          NaN            NaN       NaN       NaN       NaN                       0                      0               NaN INCONCLUSIVE
SYNTHETIC_DEMO     C_H3_VU_LOCAL_BURST             1           1 HYPOTHETICAL_T1_OPEN_PRICE                 1                       0     0.000674       0.000674  1.000000  0.008760 -0.005166                       1                      0               NaN INCONCLUSIVE
SYNTHETIC_DEMO     C_H3_VU_LOCAL_BURST             3           1 HYPOTHETICAL_T1_OPEN_PRICE                 1                       0     0.090746       0.090746  1.000000  0.092318 -0.005166                       1                      0               NaN INCONCLUSIVE
SYNTHETIC_DEMO     C_H3_VU_LOCAL_BURST             5           1 HYPOTHETICAL_T1_OPEN_PRICE                 1                       0     0.113432       0.113432  1.000000  0.114331 -0.005166                       1                      0               NaN INCONCLUSIVE
SYNTHETIC_DEMO     C_H3_VU_LOCAL_BURST            10           1 HYPOTHETICAL_T1_OPEN_PRICE                 1                       0     0.159479       0.159479  1.000000  0.172507 -0.005166                       1                      0               NaN INCONCLUSIVE
SYNTHETIC_DEMO     C_H3_VU_LOCAL_BURST            20           1 HYPOTHETICAL_T1_OPEN_PRICE                 0                       1          NaN            NaN       NaN       NaN       NaN                       1                      0               NaN INCONCLUSIVE
```
