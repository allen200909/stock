# MBV V0.1 接手交接书 — R5 完成情况、缺陷和下一 Agent 的实施计划

**发布日期：2026-11-11｜任务：R5 WIP → R6 端到端修复与 V0.1 G0 验收**

> **总判断：R5 有真实代码进展，但尚未交付可用的 MBV V0.1。G0 = FAIL；G1 = BLOCKED_REAL_DATA；G2 = NOT VERIFIED；G3 = NOT TESTED。禁止据此出具真实交易有效性结论或合并 master。**

## 0. 第一件事：锁定正确的源码版本

- **本交接书的唯一代码依据**：用户上传的 `MBV_V0.1_Carbon_Completed_R5.zip`（ZIP SHA-256：`10f9e12ae4f0ad70f561ffd626a2dee2fd991ab845971b6923613aee84991927`）。
- ZIP 包含 28 个条目（其中有 Windows 反斜杠路径，需规范化解压）。关键 R5 Python 目录为 `mbv/`、`tests/`、`data_adapters/`、`config/`、`reference/`、`run_demo.py`。
- **重要版本警告**：当前 GitHub `feature/vlr-microburst-v0` 的 `mbv/*.py` 是先前上传的早期 WIP 原型，**不是 R5 最新代码**。本次仅把交接文档同步 GitHub；**不得从 GitHub 现有旧源码重新开发并称为 R5 续作**。新 Agent 必须同时获得用户的 R5 ZIP，先解压校验，再在 R5 源码上增量开发。无法获得正确 ZIP 时应报告 `BLOCKED_SOURCE_SNAPSHOT`，不得假装已有 R5 源码。
- 本项目稳定 B0/VLR V2.1.2 冻结基线在 `projects/tdx-volume-liquidity-residual/`；R5 ZIP `reference/vlr_verify/` 是研究用只读快照。不得修改冻结的 TDX 指标、三个选股公式或 B0 定义。
- 第三方 Zeiierman Pine v6 文件在 `reference/third_party/`，保留 CC BY-NC-SA 4.0 与署名；不能当作仓库 Apache-2.0 下可自由移植的代码。
- **开发分支**：`feature/vlr-microburst-v0`；本阶段请在新 Agent 环境编写、测试，并采用独立工作分支或本地工作目录；不允许未经人工复核合并 master。

## 1. 当前 R5 完成的部分：区分“已实现”与“已验证”

| 文件 / 子系统 | R5 已有代码与正面证据 | 当前验收边界 |
|---|---|---|
| `mbv/schema.py` | `DataContractError`、标识/数值/OHLC/日线约束等校验工具 | 只覆盖部分输入组合；尚无全链路数据契约验收 |
| `mbv/sessions.py` | A 股上午/下午交易槽位、1m/5m、`bar_start`/`bar_end`、单位换算及 `validate_minute_bars`；R5 现有测试通过 | 仍需边界、收盘集合竞价、真实源时间戳兼容性回归 |
| `mbv/baselines.py` | 过去20个交易日同证券同槽位滚动中位数；`shift(1)`/历史正量样本≥15；独立检查局部通过；有 EMA 基准对照实现 | 没有真实市场日历验证；底层输入依赖已正确规范化 |
| `mbv/features.py` | 通过完整 `(symbol, trade_date, time_slot)` 键关联基准；`rel_vol≥2.5` 与 `|body_efficiency|≥0.10`；零基准防 `inf`；局部测试通过 | 最终日线信号与 prefix invariance 尚未通过 |
| `mbv/aggregate.py` 私有函数 `_aggregate_one_session()` | 对构造的48槽位/双向爆量单日样本，局部得到 count/share/peak/dominance/HHI/coverage/reconciliation 等合理结果 | **公开 `aggregate_daily_features()` 仍是 Stub，直接返回空表；不能算已完成的日线聚合** |
| `mbv/join.py` | 只读 B0 桥、主键检查、缺分钟状态；单行缺分钟与重复日键探针通过 | 全链路未通过；部分 point-in-time 状态缺少正式测试 |
| `mbv/adapters.py` / `data_adapters/__init__.py` | 本地 CSV/Parquet 数据加载结构、合成数据生成器与 QMT/PTADE 环境探测接口 | 未连接真实 QMT/PTADE 数据；Parquet 依赖/字段口径需现场验证 |
| `mbv/cli.py` 与 `run_demo.py` | CLI 子命令、SYNTHETIC_DEMO 工作流已编写 | **一键演示失败**；未生成可信、非空、可复现的联合日线报告 |
| `mbv/event_study.py` | T+1 forward outcome、同日 RVOL 对照匹配、置换负对照和区块 bootstrap 调用骨架 | 仅代码存在：统计逻辑有待修复，未通过 T16–T19 验收 |
| `config/default.yaml` / `SPEC.md` / `DATA_CONTRACT.md` / `THREAT_MODEL.md` | 频率、时区、阈值、缺失语义、研究范围已有显式文字配置 | 文档描述不等于执行代码通过；以真实函数行为和测试为准 |
| `tests/test_baselines_and_prefix.py`、`tests/test_sessions_and_validation.py` | 现有9个 pytest case | **7 PASS / 2 FAIL**；距离 T01–T20 全面验收仍远 |

**特别保留的正确方向**：日内时段季节性通过同证券/同槽位历史基准处理；爆量为分钟 OHLCV 方向代理，不是真实主动买卖单或资金净流；保留日线 B0 原信号且不直接输出买卖执行指令。

## 2. 独立复测结果与阻断证据

依据 R5 ZIP 本地标准化解压后，在 Linux / Python **3.13.5** 上复测：

```shell
PYTHONPATH=. python -m pytest -q tests -ra
# 7 passed, 2 failed (失败 T02 和 T03)

PYTHONPATH=. python -m pytest --cov=mbv --cov-report=term-missing -q tests -ra
# 7 passed, 2 failed；TOTAL coverage 37% (1240 statements, 787 missed)

python run_demo.py
# 失败：mbv.schema.DataContractError: Missing primary key column 'symbol' in mbv_features
```

**根因已定位、可直接修复**：

```python
# R5: mbv/aggregate.py
def aggregate_daily_features(...):
    if df.duplicated(subset=["symbol", "trade_date", "time_slot"]).any():
        raise DataContractError(...)
    # ... session exclusion & groupby loops ...
    return pd.DataFrame()  # Stub
```

该函数永远输出 **0 行 0 列**。所以 `test_t02_end_to_end_prefix_invariance` 读取 `trade_date` 时报 `KeyError`，`test_t03_cross_symbol_isolation_in_baseline_burst_and_aggregation` 读取 `symbol` 时报 `KeyError`；演示链路调用 `join_daily_vlr_mbv` 时缺少主键 `symbol`。这不是“输入样本效果差”，而是功能缺失。

**注意**：`_aggregate_one_session()` 对一个人工单日夹具计算正确，不能替代公开聚合的多证券/多日/覆盖率/状态测试。

## 3. 必须优先修复的工作包（按照顺序执行）

### WP-A（P0，禁止扩项）：让公开日线聚合真正运行

1. 实现 `aggregate_daily_features(df, frequency, exclude_closing_auction, daily_ref, ...)`：严格校验输入列、`(symbol,trade_date,time_slot)` 唯一性/非空、数值有效性；按 `(symbol,trade_date)` 分组并调用已存在的 `_aggregate_one_session()`；输出稳定的全字段表及列序、类型与唯一键。
2. 规范 1m=240/5m=48 标准交易槽位；是否排除收盘集合竞价应按 `frequency` 定义并同步调整分母，不得少一组槽位却仍用旧分母。不可默默丢弃异常槽位。
3. 处理 `daily_ref` 的非空、主键唯一、日线 `volume` 与 `DIR` 一对一关联；实现分钟/日线成交量对账、`reconciliation_tol`，不因缺失把结果伪造为零。
4. 状态优先级固定并回归验证：`NO_VOLUME` / `LOW_COVERAGE` / `INSUFFICIENT_HISTORY` / `OK`；非可用日 count/share/方向/集中度必须为 **NA + status**。合法无爆量日才是 `feature_status=OK, burst_count=0, burst_share=0`。
5. 覆盖率阈值默认 95%；标注 `valid_slot_coverage` 与 `baseline_slot_coverage`，区分“分钟K缺失”与“有效历史基准不足”。
6. 检查 HHI 归一化、`burst_count=1` 特例、正负方向抵消、日线 DIR 一致性；输出对应 `burst_regime`，但不要把任何值描述为真实主动资金流。
7. 空输入要么返回带固定 schema 的空表并明确状态、要么以 `DataContractError` 失败；禁止无列空表直接进入 join。

**WP-A 完成标准**：T02/T03 真正 PASS，`python run_demo.py` 输出非空 MBV 日表、非空 B0+MBV 左关联表和带 `SYNTHETIC_DEMO` 标签的研究报告。T 日已确认的 B0 信号记录不得消失或翻倍。

### WP-B（P0/P1）：补齐工程回归和可复现输出

1. 对关键入口进行多证券/多日期端到端前缀不变性；过去日期的所有数值、状态和爆量标记都不得受未来日期追加影响。
2. 加入集中爆量 vs 均匀放量、单次爆量、双向对冲、0成交/缺历史/低覆盖/重复主键、1m/5m、午休与 14:57–15:00 收盘集合竞价的边界测试。
3. `compute_mbv_daily_pipeline` 目前信任输入已规范化，应明确其输入契约，或者在此入口重新验证；禁止任何未经验证的分钟表进入正式主链。
4. 一键演示必须固定随机种子，生成合法 OHLCV + 完整交易日历 + 日线对账样本；提供 CSV/Parquet（如适用）的输出路径、摘要统计、配置及环境哈希。
5. 保证运行 `pytest` 全量收集且无空断言、`assert True`、伪造 PASS；报告每个 T 编号对应真实断言路径和失败原因，执行结果需有日志。

### WP-C（P1）：统计研究层修复（在 WP-A/B 正常后）

1. `permutation_negative_control()` 的文档宣称按 RVOL 桶置换，但实际对整段 `burst_share` 直接调用 `rng.permutation(shares)`。须**仅在预先冻结的 RVOL 分桶内置换**，保留桶内样本量；空桶/不足样本报告 INCONCLUSIVE。
2. `match_controls_same_date_rvol()` 当前找不到同板块候选时静默退回不同板块，应根据研究计划规定 **严格匹配或显式标记放宽条件**；不能“默默换对照”。
3. 未来收益仅作标签，在 T 日特征构建中不出现 `fwd_ret_*`。T 收盘确认、最快 T+1 执行；交易日历不可用时阻止正式事件研究。
4. 使用历史已对拍确认的 B0 只读 API；保持不同数据状态与不可成交状态独立，不用日线 OHLC 猜测开盘必定能成交。
5. 缺少对照组/观察不足时结果为 `INCONCLUSIVE`，不凭 synthetic demo 得出 alpha。
6. 继续调用既有 `reference/vlr_verify/inference.py` 的 calendar-block bootstrap；报告随机种子、区块长度敏感性和缺失样本。

### WP-D（P2）：真实数据 / 运营前置（不能伪造通过）

- G1：真实 QMT/PTADE 1m/5m 分钟行情、交易所日历、lot/share、时间戳语义、午休、集合竞价、复权/成交量口径和日-分钟成交量对账；
- G2：VLR B0 真实通达信全 21 条输出逐 K 对拍（当前仍未完成）；
- G3：真实按日期/RVOL（必要时板块）匹配对照、1/3/5/10/20 日 forward returns、MFE/MAE、成本、成交可行性、区块 bootstrap 与全新预先登记确认样本；此前查看过的2021–2026分布不能冒称封存 OOS。

G1–G3 所需真实资料未提供时，完成可以离线完成的代码，明确标 `BLOCKED_REAL_DATA` / `PROVISIONAL_RESEARCH` / `NOT_TESTED`，不反复要求用户提供已有材料，也不得伪造回测数据。

## 4. T01–T20 逐项接手状态（独立实测 / 尚未验证）

| ID | R5 状态 | 新 Agent 必须提交的验收证据 |
|---|---|---|
| T01 | LIMITED PASS | 单日当前值不污染历史同槽位基准；进一步加时间边界 |
| T02 | **FAIL** | 多日全流水线前缀不变性；公开聚合非空 |
| T03 | **FAIL** | 混合多证券 vs 单证券独立计算全流水线一致 |
| T04 | LIMITED PASS | 午休与其他非法时段拒绝，真实会话边界 |
| T05 | LIMITED PASS | bar_start / bar_end 规范化与歧义拒绝 |
| T06 | LIMITED PASS | 1m/5m 240/48槽、收盘集合竞价/排除后的分母 |
| T07 | LIMITED PASS | OHLC、负量、NaN/Inf、重复分钟键、零基准 |
| T08 | NOT VERIFIED | 95%覆盖率与 NA/status 门禁 |
| T09 | LIMITED PASS | 过去20日内 ≥15 个正量同槽位样本及零量排除 |
| T10 | HELPER ONLY | 日内计数、爆量占比、方向优势、HHI及单次样本 |
| T11 | NOT TESTED | 均匀放量与集中爆量可区分 |
| T12 | PARTIAL | B0 左联无分钟日保留，NA + MISSING_MINUTE_DATA |
| T13 | NOT TESTED | PIT 风险标签、停复牌、涨跌停等原始事件与可交易性分离 |
| T14 | PARTIAL | 两边日键/分钟键唯一非空、严格 cardinality |
| T15 | NOT TESTED | B0 不变性/只读桥回归及源哈希验证 |
| T16 | NOT TESTED | 缺真实交易日历时正式事件研究拒绝 |
| T17 | NOT TESTED | T日因子与未来收益标签完全隔离 |
| T18 | NOT TESTED | 匹配对照不足时 INCONCLUSIVE；不静默放宽板块 |
| T19 | NOT TESTED | 区块 Bootstrap 真实调用和手算夹具 |
| T20 | **FAIL** | `python run_demo.py` 一键成功生成非空 SYNTHETIC_DEMO 输出及报告 |

`LIMITED PASS` 只是已有受限测试通过，**不是 T01–T20 全套验收通过**。

## 5. 新 Agent 操作入口与最小命令

1. 解压用户提供的 **R5 ZIP**，把 ZIP 中 Windows 分隔符 `\` 规范为 POSIX `/`；拒绝 `../` 路径穿越和绝对路径覆盖；删除 `__pycache__`、`.pytest_cache`、旧 `.coverage` 后建立干净工作树。
2. 保留 `reference/` 全部文件只读，确认 R5 ZIP SHA；完成 WP-A、WP-B 再推进 WP-C。
3. 建议在 `mbv/aggregate.py` 主接口上修复，而不是再造同名新函数绕过测试。

```bash
python -m pip install "numpy>=1.26,<3" "pandas>=2.1,<3" "PyYAML>=6,<7" "pytest>=8,<10" "pytest-cov>=5,<10"
PYTHONPATH=. python -m pytest -q tests -ra
PYTHONPATH=. python -m pytest --cov=mbv --cov-report=term-missing -q tests -ra
python run_demo.py
```

4. 每次交付包含：源码/测试/配置/README、原始 pytest 日志、覆盖率报告、demo 输出样本、各 T 项状态、验证命令、数据源/代码哈希、剩余门禁；压缩包 UTF-8、路径使用 `/`、排除缓存；若 GitHub 可用，在**新开发分支**提交并提供 SHA；若不可用则以完整 ZIP 回传。
5. 本阶段不要改变阈值来美化回测结果；不修改 VLR V2.1.2 冻结公式、不合并 master、不生成自动交易执行。

## 6. R6 完成定义及决策门槛

**第一个里程碑（强制）**：T02、T03 和 T20 全部通过；公开聚合有完整 schema，B0+MBV 联合表不丢失或复制记录，G0 的已知安全缺陷不复现。

**第二个里程碑**：至少 T01–T09、T12、T14 形成完整、可核查、独立的真实自动化断言；其余 T10–T11/T13/T15–T20 按 RFC 补齐；全部计划 T01–T20 通过才可以称“V0.1 代码级 G0 通过”。

**第三个里程碑**：G1/G2/G3 均有独立真实数据证据才允许讨论“指标增量是否成立”或潜在合并。若真实数据暂缺，最多验收 G0 工程模块，绝不能声称策略 alpha。

## 7. 需二次独立审查的问题

- rolling TOD 的“过去20日”是否严格按**交易所完整交易日历**而非仅存在行情的日期移动；缺日会否使基准跨越过长时间；
- 1m/5m 槽位、收盘竞价排除和覆盖率/对账分母是否完全一致；
- NA/status 是否贯穿 features、aggregate、join、event study；
- HHI 单爆量、多爆量与双向抵消在不同极端值下是否稳定；
- 统计对照的 RVOL 条件化、板块约束、标签泄漏和股票/日期交叉依赖；
- B0 冻结参考完整性、第三方许可隔离和真实数据口径。

**交付原则**：只把有代码、有运行输出、有真实断言的内容记作完成。R5 不是失败重做的理由；先复用已实现的模块，修复阻断路径，逐项验收后推进。
