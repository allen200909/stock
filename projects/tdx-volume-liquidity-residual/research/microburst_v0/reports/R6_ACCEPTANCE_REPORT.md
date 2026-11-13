# MBV V0.1 — R6 验收报告（R5 → R6，WP-A / WP-B / WP-C）

- **日期**：2026-11-12
- **分支**：`feature/vlr-microburst-v0-r6`（从 `origin/feature/vlr-microburst-v0` 切出；**未合并 master**）
- **代码基线**：用户上传的 `MBV_V0.1_Carbon_Completed_R5.zip`
  - SHA-256 `10f9e12ae4f0ad70f561ffd626a2dee2fd991ab845971b6923613aee84991927`，28 个 ZIP 条目（已核对）
  - 解压方式：`\` 规范为 `/`，拒绝 `../` 穿越和绝对路径；导入提交 `3e856b3` 与 ZIP 内容逐字节一致（0 处不一致）；
    `reference/` 与 ZIP 完全一致（`diff -r` 结果为空）
- **研究标签**：仅 `SYNTHETIC_DEMO`。**本报告不给出任何 alpha 或交易有效性结论。**

> **门禁状态**：G0（代码级）= **T01–T20 自动化测试全部 PASS（见 §3）**，最终签收需独立复核 ·
> G1 = **BLOCKED_REAL_DATA** · G2 = **NOT_VERIFIED** · G3 = **NOT_TESTED**

## 1. R5 基线复现（修改前）

环境：Linux，Python 3.11.2，venv（numpy 2.4.6，pandas 2.3.3，PyYAML 6.0.3，pytest 9.2.0，pytest-cov 7.1.0，pyarrow 26.0.1）。

| 检查项 | 交接书（Python 3.13.5） | 本次复现（R5 ZIP 原样） |
|---|---|---|
| `pytest -q tests -ra` | 7 passed / 2 failed（T02、T03） | **7 passed / 2 failed**（T02、T03 均为 `KeyError`） |
| 覆盖率 | 37%（1240 条语句，未覆盖 787） | **37%（1240 条语句，未覆盖 787）** |
| `python run_demo.py` | `DataContractError: Missing primary key column 'symbol' in mbv_features` | **相同错误** |

根因已确认：R5 的公开函数 `aggregate_daily_features()` 是 stub，固定返回 `pd.DataFrame()`。

## 2. 改动内容（在 R5 上增量修改，没有重写）

| 提交 | 工作包 | 内容 |
|---|---|---|
| `3e856b3` | 导入 | 原样导入 Carbon R5 源码快照，替换 GitHub 上旧的 WIP `mbv/` |
| `24e9f23` | **WP-A** | 实现公开的 `aggregate_daily_features()`：严格校验输入列、`(symbol,trade_date,time_slot)` 唯一且非空、数值合法；按 `(symbol,trade_date)` 分组后调用 R5 已有的 `_aggregate_one_session()`；输出列顺序、类型固定（`AGG_OUTPUT_COLS`）；空输入返回固定 schema 的空表；收盘集合竞价排除会同步调整分母（5m：48→47，1m：240→237）；`daily_ref` 唯一性检查、成交量对账、`B0_DIR`/`DIR` 方向一致性；状态优先级 `NO_VOLUME > LOW_COVERAGE > INSUFFICIENT_HISTORY > OK`，非 OK 日的指标一律为 NA；有爆量但方向权重为零时返回 `DIRECTIONLESS_BURSTS` |
| `0884011` | **WP-B** | `compute_mbv_daily_pipeline` 入口重新调用 `validate_minute_bars`（契约为 bar_start、share、配置频率），并拒绝 forward 列；`build_tod_baseline(trading_calendar=…)` 让 20 日窗口按**交易所日历**步进，缺失日也占一个窗口位，日历外的日期直接报错；`assert_frozen_vlr_integrity()`：三个参考文件 SHA-256 不符即失败退出；demo 固定随机种子，检查 B0 行数和事件数不变，同时输出 CSV 和 Parquet，并生成 `run_manifest.json`（不含时间戳：输入、输出、代码 SHA-256，环境，门禁）；修复 `FutureWarning`；新增 `pytest.ini`，把 `FutureWarning`/`RuntimeWarning` 视为错误 |
| `0abb5d5` | **WP-C** | Group E 置换改为**只在冻结的 `B0_RVRAW` RVOL 桶内进行**，保持每桶样本量；输出 seed、置换次数、各桶计数、双侧 p 值；RVOL 缺失或没有可置换的桶时为 INCONCLUSIVE。匹配对照新增 `board_policy`（默认 `strict`，放宽板块只能显式选 `relax_explicit` 并计数，`ignore` 会单独标注）；RVOL 为 NaN 的样本记为未匹配并计数；匹配使用 seed。T+1 状态把 `DATA_MISSING` 和 `UNFILLED_SUSPENDED_T1` / `UNFILLED_LOCKED_T1` / `UNFILLED_LIMIT_UP_T1` 分开；没有 PIT 状态列时记为 `TRADABILITY_UNVERIFIED_T1`（只算假设收益，不声称能成交）。bootstrap 继续调用只读的 `inference.block_bootstrap`，评估日历取分钟数据覆盖区间，并报告 seed、区块长度敏感性、因区块过长而剔除的长度、因收益缺失而剔除的事件数。结果中包含 `conclusion`（不出 alpha 结论）和 `gates`。新增 `config/default.yaml` 键：`board_policy`、`matching_seed`、`permutation_n`、`permutation_seed`（**原有阈值均未改动**） |

## 3. T01–T20 验收矩阵（实际断言路径）

完整日志：[pytest_log.txt](r6/pytest_log.txt)，**90 passed / 0 failed / 0 warnings**（`FutureWarning`、`RuntimeWarning` 已设为 error）。R5 原有的 9 个测试未作任何修改，现在全部通过。

| ID | 结果 | 测试（文件::函数） |
|---|---|---|
| T01 | PASS | `test_baselines_and_prefix.py::test_t01_current_and_future_volume_never_leak_into_baseline`；`test_pipeline_e2e_wp_b.py::test_t01_current_future_and_other_slot_changes_do_not_move_baseline_at_t` |
| T02 | PASS | `test_baselines_and_prefix.py::test_t02_end_to_end_prefix_invariance`（R5 原测试）；`test_pipeline_e2e_wp_b.py::test_t02_multi_symbol_multi_date_end_to_end_prefix_invariance[False/True]`；`test_event_study_t16_t19.py::test_t17_t_day_features_unaffected_by_appending_future_minute_and_daily_data` |
| T03 | PASS | `test_baselines_and_prefix.py::test_t03_cross_symbol_isolation_in_baseline_burst_and_aggregation`（R5 原测试）；`test_pipeline_e2e_wp_b.py::test_t03_mixed_vs_single_symbol_full_pipeline_and_input_order_independence` |
| T04 | PASS | `test_sessions_and_validation.py::test_t04_…`；`test_pipeline_e2e_wp_b.py::test_t04_lunch_break_not_missing_and_post_lunch_seasonality_not_a_fake_burst`、`test_t04_t05_1min_session_boundaries_bar_start_and_bar_end` |
| T05 | PASS | `test_sessions_and_validation.py::test_t05_…`；`test_pipeline_e2e_wp_b.py::test_t04_t05_1min_session_boundaries_bar_start_and_bar_end`、`test_pipeline_is_idempotent_on_validated_input_and_never_double_shifts_or_converts` |
| T06 | PASS | `test_sessions_and_validation.py::test_t06_…`；`test_aggregate_wp_a.py::test_t06_5min_closing_auction_exclusion_…`、`test_t06_1min_240_and_237_denominators_in_aggregation`；`test_pipeline_e2e_wp_b.py::test_t06_1min_pipeline_closing_auction_included_vs_excluded` |
| T07 | PASS | `test_sessions_and_validation.py::test_t07_…`；`test_aggregate_wp_a.py::test_t07_t14_aggregation_input_contract_rejections`（11 个参数组合）；`test_pipeline_e2e_wp_b.py::test_pipeline_revalidates_input_and_rejects_unvalidated_minute_tables`（7 个） |
| T08 | PASS | `test_aggregate_wp_a.py::test_t08_coverage_gate_95pct_and_na_plus_status`、`test_t08_status_priority_…`、`test_t08_pipeline_low_coverage_and_insufficient_history_days_are_na_with_status` |
| T09 | PASS | `test_baselines_and_prefix.py::test_t09_15_to_19_positive_days_valid_and_zero_volumes_excluded`；`test_pipeline_e2e_wp_b.py::test_exchange_calendar_stepping_counts_missing_sessions_in_the_20_session_window` |
| T10 | PASS | `test_aggregate_wp_a.py::test_t10_zero_bursts_…`、`test_t10_single_burst_…`（2 个）、`test_t10_two_way_offsetting_bursts_cancel`、`test_t10_hand_computed_weights_hhi_and_direction_agreement`、`test_t10_directionless_bursts_keep_ok_counts_not_nan` |
| T11 | PASS | `test_aggregate_wp_a.py::test_t11_concentrated_microbursts_vs_uniform_volume_expansion_are_distinguished` |
| T12 | PASS | `test_join_b0_t12_t15.py::test_t12_left_join_preserves_every_b0_row_and_never_zero_fills`、`test_t12_empty_mbv_table_yields_all_missing_with_fixed_schema` |
| T13 | PASS | `test_join_b0_t12_t15.py::test_t13_point_in_time_risk_tags_and_eligibility`、`test_t13_missing_status_columns_never_fabricate_tradability`、`test_t13_suspended_row_through_b0_and_join_is_flagged` |
| T14 | PASS | `test_join_b0_t12_t15.py::test_t14_duplicate_and_null_keys_rejected[left/right]`、`test_t14_missing_contract_columns_raise_contract_error_not_keyerror`；`test_aggregate_wp_a.py::test_t07_t14_…`、`test_daily_ref_reconciliation_statuses_and_duplicate_keys` |
| T15 | PASS | `test_join_b0_t12_t15.py::test_t15_readonly_b0_equals_direct_frozen_reference_calculation`、`test_t15_reference_snapshot_hashes_match_frozen_constants_and_repo_verify`、`test_t15_frozen_vlr_v212_indicator_selectors_verify_files_unchanged`、`test_t15_tampered_reference_copy_fails_closed` |
| T16 | PASS | `test_event_study_t16_t19.py::test_t16_calendar_gate_fails_closed`（5 个）、`test_t16_dates_outside_calendar_rejected_and_calendar_gap_is_data_missing` |
| T17 | PASS | `test_event_study_t16_t19.py::test_t17_forward_columns_rejected_…`、`test_t17_outcomes_are_a_separate_table_…`、`test_t17_t_day_features_unaffected_…`、`test_t17_t1_tradability_states_are_distinct_…` |
| T18 | PASS | `test_event_study_t16_t19.py::test_t18_strict_board_never_silently_falls_back`、`test_t18_explicit_relaxation_is_counted_…`、`test_t18_insufficient_or_missing_inputs_are_inconclusive`、`test_t18_run_event_study_without_events_is_inconclusive_everywhere` |
| T19 | PASS | `test_event_study_t16_t19.py::test_t19_bootstrap_constant_returns_give_degenerate_ci`、`test_t19_wrapper_equals_independent_reimplementation_on_tiny_calendar`、`test_t19_bootstrap_sparse_events_raise_…`、`test_t19_within_bucket_permutation_preserves_bucket_composition`、`test_t19_group_e_permutes_only_within_rvol_buckets_…`、`test_t19_group_e_inconclusive_paths` |
| T20 | PASS | `test_demo_t20.py::test_t20_demo_exits_zero_with_non_empty_outputs`、`test_t20_report_is_labelled_synthetic_…`、`test_t20_two_runs_are_byte_reproducible`（以子进程方式真实运行 `run_demo.py` 两次）；`test_cli_chain.py`（CLI 分步链路结果与 demo 一致） |

## 4. 覆盖率

[coverage.txt](r6/coverage.txt) / [coverage.xml](r6/coverage.xml)：**TOTAL 89%（1509 条语句，未覆盖 167）**；R5 为 37%。

| 模块 | 覆盖率 | 模块 | 覆盖率 |
|---|---|---|---|
| aggregate.py | 94% | join.py | 95% |
| cli.py | 93% | event_study.py | 92% |
| schema.py | 89% | sessions.py | 88% |
| adapters.py | 84% | features.py | 79% |
| baselines.py | 66%（主要未覆盖的是可选的 `compute_session_ema_benchmark` 基准，以及部分输入校验分支） | | |

## 5. 一键 demo（`python run_demo.py`，无参数）

日志：[demo_run_log.txt](r6/demo_run_log.txt)（`exit_code=0`）；输出样本：[demo_outputs/](r6/demo_outputs/)（Parquet 因体积未纳入提交，运行时会生成，日志中为 `parquet: WRITTEN`）。

- 分钟数据 6480 行（3 只证券 × 45 个交易日 × 48 个槽位），日线 510 行，MBV 日表 135 行（OK 90，INSUFFICIENT_HISTORY 45）
- B0+MBV 联合表 510 行，与日线行数一致（MISSING_MINUTE_DATA 375）；经过 join 后 B0 事件数不变：EU 8 / ABU 1 / VU 1
- 研究层（仅 SYNTHETIC_DEMO）：H1/H2 匹配对照在 `strict` 板块约束下为 **INCONCLUSIVE**（没有同日、同 RVOL 桶、同板块的候选）；Group E 只在 1 个 RVOL 桶内可置换，n=6，状态 `COMPLETED`，p=0.339，标注 `interpretation=NOT_EVIDENCE_SYNTHETIC`；bootstrap 评估窗口 45 个交易日，B 组 9 个事件中 7 个可用，2 个因收益缺失被剔除
- 报告结论：`NO_RESEARCH_CONCLUSION`；同时声明本研究使用的是 OHLCV 代理，不是 order-flow
- 两次运行的 `run_manifest.json` 逐字节一致（T20 测试已断言）

## 6. 哈希

| 对象 | SHA-256 |
|---|---|
| R5 ZIP | `10f9e12ae4f0ad70f561ffd626a2dee2fd991ab845971b6923613aee84991927` |
| reference/vlr_verify/vlr.py（= ../../verify/vlr.py） | `3dfba129c22282b3409a0d32f6781638b0699d8c1d2393e81a0cd8ec7b3f07b8` |
| reference/vlr_verify/validation.py | `bc647ac1e64753a1bc2af15525a755b9162f646acd99e299a475ee96cc5a12d3` |
| reference/vlr_verify/inference.py | `ed2243298785c93755f2a5cf20e5f9d930b544ce2e6523f9703508a07732bef1` |
| indicator/volume_liquidity_residual_v2.1.2.tdx | `9913cceddbb5e58450c0e8a883c5b8b82217d02d574765c80503b3715564fcad` |
| selectors/strong_expansion_3d.tdx | `31a00ebaaac95784672be21ad8a5a0a27accc57b5e7b0fddfbd227fd32173da4` |
| selectors/strong_expansion_60d3_recent10.tdx | `2cb07ba1825932d38eea88d7c6e911abf18c98739bcc13558948dc7e0245fd9b` |
| selectors/strong_expansion_activity_layered.tdx | `99c46e672f04741ed04165a626f2f85db8f375626636a50ba812ab2921365886` |
| mbv/aggregate.py | `58bf5d2d9bb52c6282c14aa8f4f6da829546a257873189744202093d1e472d5f` |
| mbv/baselines.py | `c86219d9e025448cb05b262969128b685e20978744b5a50462a13c9498db5267` |
| mbv/cli.py | `76977dfc865e5cdf169aa3a893a3006021fd4100ef7b9c8246d713663e5b030d` |
| mbv/event_study.py | `11d9c873ab14029a99c036b0a5b18ff148f86112517f4ec541ce8f29661c442e` |
| mbv/join.py | `9b28cb894bc119568270d8ae5d884df9ada4d7440abba7be707a0f0533a55897` |
| mbv/features.py / schema.py / sessions.py / adapters.py | 与 R5 相同：`f73abdf4…`、`bff4987a…`、`c214ba16…`、`0fe6ec71…` |
| config/default.yaml | `226e45ca100f30363360abace32a1777fe64cd766568e9a1f3d8101e0a340d6f` |

冻结基线：`git diff origin/master -- projects/tdx-volume-liquidity-residual/{indicator,selectors,verify}` 结果为**空**，T15 测试也对这些文件的 SHA-256 做了断言。

## 7. 复核命令

```bash
cd projects/tdx-volume-liquidity-residual/research/microburst_v0
python -m pip install "numpy>=1.26,<3" "pandas>=2.1,<3" "PyYAML>=6,<7" "pytest>=8,<10" "pytest-cov>=5,<10" pyarrow
python -m pytest -q tests -ra                      # 期望 90 passed
python -m pytest --cov=mbv --cov-report=term-missing -q tests
python run_demo.py                                 # exit 0，输出写入 examples/demo_outputs/
```

## 8. 局限与待独立复核的问题

1. **G1 BLOCKED_REAL_DATA**：尚未接入真实 QMT/PTADE 1m/5m 行情、交易所日历、lot/share 口径、集合竞价和复权口径；`data_adapters` 的环境探测仍未经验证。
2. **G2 NOT_VERIFIED**：B0 只与仓库内只读 Python 参考做了一致性测试（T15），**尚未与通达信真实 21 列输出逐 K 对拍**。
3. **G3 NOT_TESTED**：没有真实样本、成本模型或预先登记的 OOS 样本；synthetic 结果不能作为证据。
4. 交易所日历步进是**可选参数**：CLI `compute-features --calendar` 和 demo 都会传入日历，不传时退化为该证券有数据的日期（与 R5 行为一致）。正式研究时应强制传入日历，需复核方确认是否改为必填。
5. T+1 可成交性依赖 PIT 状态列（`suspended`、`price_limit_status`）。“开盘即涨停”仅以 `open >= high` 且状态为 LIMIT_UP 判定，属保守近似，需真实涨跌停价数据复核。
6. `relax_explicit` / `ignore` 板块策略只为敏感性分析保留，默认 `strict`；Group E 在可置换桶很少时 p 值没有意义，报告中已注明 `interpretation`。
7. 交接书 §7 列出的问题（窗口按完整交易所日历步进、1m/5m 分母一致性、NA/status 贯穿全链路、HHI 极端值、RVOL 条件化与交叉依赖、B0 完整性与第三方许可隔离）已有对应测试，但仍需独立复核。`third_party/` 中的 Zeiierman Pine（CC BY-NC-SA 4.0）未被引用，也没有被移植。
