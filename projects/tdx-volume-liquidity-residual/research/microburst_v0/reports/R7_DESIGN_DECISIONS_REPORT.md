# MBV V0.1 — R7 设计决定实施报告

- **日期**：2026-11-13
- **分支**：`feature/vlr-microburst-v0-r7`（从 R6 HEAD `2c100f8` 切出；**未合并 master**）
- **代码提交**：`2770bd7`（代码 + 测试）；本报告及证据另行提交
- **研究标签**：demo 仅为 `SYNTHETIC_DEMO`。**不给出任何 alpha 或交易有效性结论。**

> 门禁：G1 = **BLOCKED_REAL_DATA** · G2 = **NOT_VERIFIED** · G3 = **NOT_TESTED**（与 R6 相同，未改动）

## 1. 交易所日历（决定 §1）

新模块 [calendar_policy.py](../mbv/calendar_policy.py)，`compute_mbv_daily_pipeline()`、CLI `compute-features` / `study`、`run_event_study()` 统一调用 `resolve_study_context()`。

| 模式 | 日历要求 | 其他要求 | `calendar_kind` | research_grade |
|---|---|---|---|---|
| `SYNTHETIC_DEMO` | 可选；demo 固定传入生成日历 | 事件研究仍必须传日历（T16） | `SYNTHETIC_GENERATED`；特征管线未传日历时为 `NONE_SYMBOL_OBSERVED_DATES` | `SYNTHETIC_DEMO_ONLY` |
| `EXPLORATORY_REAL_DATA` | **必填** | 来源记录：`kind=EXCHANGE`、非空 `source` / `verified_by`、`verified: true`（布尔值，字符串无效）、`calendar_sha256` = 所传日历的指纹 | `EXCHANGE` | `PROVISIONAL_RESEARCH` |
| `CONFIRMATORY_OOS` | **必填** | 同上 + 预登记记录（`registry_id`、`registered_on`、`sample_start`、`sample_end`、`data_source`、`document_path`、`document_sha256`）：文档必须存在且哈希一致；`registered_on < sample_start ≤ sample_end`；窗口须在日历内；事件研究的全部交易日须在窗口内（特征管线允许窗口前的预热历史，但不允许超出 `sample_end`） | `EXCHANGE` | `CONFIRMATORY_OOS_CANDIDATE_PENDING_INDEPENDENT_REVIEW` |

- **日历一致性**：特征表新增 `calendar_kind`、`calendar_sha256`（SHA-256 of `"\n".join(YYYY-MM-DD)`）两列。事件研究要求：有分钟数据的行，其 `calendar_sha256` 必须等于研究日历的指纹（任何模式下不一致都报错）；正式模式下缺少该标记也报错。
- **不静默回退**：正式模式未传日历时直接报 `DataContractError`；只有 `SYNTHETIC_DEMO` 允许按证券行情日期滚动，且会明确标注。
- **规则未改**：20 日窗口、≥15 个正量样本的规则没有改动。测试比较了同一日历下 formal 与 synthetic 两种模式的输出，除 `calendar_kind` 外逐值相同；第 15 日之前为非 OK，之后为 OK。
- **字符串不能升级标签**：仅传 `CONFIRMATORY_OOS` 字符串、或只带来源记录而没有预登记，都会报错。即使完全有效，离线状态下也只能得到 `…CANDIDATE_PENDING_INDEPENDENT_REVIEW`，`conclusion` 仍为 `PROVISIONAL_RESEARCH_ONLY`，`gates` 不变。

## 2. T+1 开盘成交可行性（决定 §2）

在 [event_study.py](../mbv/event_study.py) 中实现 `_t1_tradability()`、`validate_execution_evidence()` 和 `build_forward_outcome_labels(execution_evidence=…)`。

**可信状态来源**：日线行的 `tradability_status_source` 非空，且不以 `SYNTHETIC` 开头。

| `t1_fill_status` | `t1_execution_class` | 触发条件 | `fwd_ret_*`（假设价格） | `exec_ret_*` |
|---|---|---|---|---|
| `PENDING_FUTURE_SESSION` / `DATA_MISSING` | `NO_DATA` | 日历中没有 T+1 / T+1 没有日线 | NaN | NaN |
| `FILLED_T1_ORDER_EVIDENCE` | `CONFIRMED_FILLED` | 订单或盘口证据 `FILLED`（优先级最高） | 保留（按开盘价） | 按**证据成交价**计算 |
| `UNFILLED_T1_ORDER_EVIDENCE` | `NOT_EXECUTABLE_CONFIRMED` | 订单或盘口证据 `NOT_FILLED` | 保留 | NaN |
| `SUSPENDED_T1_STATUS_CONFIRMED` | `NOT_EXECUTABLE_CONFIRMED` | 可信来源 + `suspended=True` | NaN | NaN |
| `TRADING_RESTRICTED_T1_STATUS_CONFIRMED` | `NOT_EXECUTABLE_CONFIRMED` | 可信来源 + `trading_restricted=True` | NaN | NaN |
| `ZERO_VOLUME_T1` | `NOT_EXECUTABLE_CONFIRMED` | 日线 `volume<=0`（来源记为 `DAILY_VOLUME`） | NaN | NaN |
| `OPEN_LIMIT_UP_FILL_UNVERIFIED_T1` | `FILL_UNVERIFIED` | 可信来源 + `price_limit_status ∈ {LIMIT_UP, LOCKED_UP}` + `open>=high`（**只作保守排除，不能据此判定未成交**） | 保留 | NaN |
| `TRADABILITY_UNVERIFIED_T1` | `FILL_UNVERIFIED` | 无可信来源（一字板、未经验证的停牌标志会写入 `t1_risk_flags`），或可信来源但状态列不完整（`STATUS_INCOMPLETE`） | 保留 | NaN |
| `ELIGIBLE_T1_OPEN_STATUS_CHECKED` | `STATUS_CHECKED_EXECUTABLE` | 可信来源，状态完整且无限制 | 保留 | 按 T+1 开盘价计算 |

- **来源字段**：`t1_status_source`、`t1_fill_evidence_source`、`t1_risk_flags`、`return_basis="HYPOTHETICAL_T1_OPEN_PRICE"`、`exec_entry_basis`（`ORDER_EVIDENCE_FILL_PRICE` / `STATUS_CHECKED_T1_OPEN`）、`exec_entry_price`。
- **证据表校验**（`--execution-evidence`；列为 `symbol, entry_date, evidence_type∈{ORDER,ORDER_BOOK}, fill_status∈{FILLED,NOT_FILLED}, fill_price, evidence_source`），以下情况一律报错：
  - 主键重复，或缺少 `evidence_source`。
  - `FILLED` 但没有正的成交价。
  - 类型或状态不合法。
  - 证据对应不上任何可用的 T+1 交易日。
  - `FILLED` 与可信来源的停牌/限制状态或零成交量相矛盾。
- **统计口径分开**：组汇总保留原有的假设收益统计（`effective_events`、`mean_return`…，标注 `return_basis`），另加 `fill_unverified_events`、`exec_effective_events`、`exec_mean_return`。FILL_UNVERIFIED 样本保留在因子研究中，但不计入 exec 统计。`exec_ret` 已加入 `FORBIDDEN_FUTURE_PREFIXES`，不允许出现在 T 日特征表中。
- **join 层同步**：`annotate_point_in_time_risk` 的 `ELIGIBLE_FOR_T1_FILL_CHECK` 同样要求可信来源，否则为 `TRADABILITY_UNVERIFIED`。
- **对 R6 的行为变化**：
  - 原 `UNFILLED_LIMIT_UP_T1` 改为 `OPEN_LIMIT_UP_FILL_UNVERIFIED_T1`；原 `UNFILLED_LOCKED_T1`（仅凭 OHLC 判定）不再存在，并入 FILL_UNVERIFIED，并带 `ONE_WORD_LOCKED` 标志。这两类现在保留假设收益，但不计入 exec 统计。
  - 原 `UNFILLED_SUSPENDED_T1` 拆分为 `SUSPENDED_T1_STATUS_CONFIRMED`（需可信来源）和 `ZERO_VOLUME_T1`。
  - 原 `ELIGIBLE_T1_OPEN_HYPOTHETICAL` 改为 `ELIGIBLE_T1_OPEN_STATUS_CHECKED`（需可信来源）。

## 3. 其他（决定 §3）

- README：已删除过时的 R5/WIP 状态说明，改为 R7 当前状态。交接书、QA 报告移入“历史记录（已过时）”一节，第三方许可说明原样保留。
- 阈值、`config/default.yaml` 没有改动（SHA-256 `226e45ca…` 与 R6 相同）。

## 4. 测试与覆盖率

完整日志：[pytest_log.txt](r7/pytest_log.txt)，**138 passed / 0 failed**（R6 为 90 个；`FutureWarning`/`RuntimeWarning` 仍视为错误）。

| 新增 / 修改 | 测试 |
|---|---|
| 决定 §1 | [test_calendar_policy_r7.py](../tests/test_calendar_policy_r7.py)（18 个）：<br>• 模拟日历标注；无日历时标为 NONE；<br>• EXPLORATORY 缺日历 / 缺来源 / kind 错误 / verified 为 False 或字符串 / verified_by 或 source 为空 / 哈希不符 / 日历不同（9 个参数组合）；<br>• 有效的 EXPLORATORY 且 gates 不变；<br>• 仅凭字符串无法获得 OOS 标签；<br>• 预登记的 6 类失败 + JSON 记录错误；<br>• 有效 OOS 仅为 CANDIDATE，窗口受约束；<br>• 管线写入日历标记，formal 与 synthetic 结果一致（20/15 规则）；<br>• 研究拒绝日历不一致 / 缺少标记 / 部分行缺少标记；<br>• CLI 正式模式必须提供日历和来源 |
| 决定 §2 | [test_t1_tradability_r7.py](../tests/test_t1_tradability_r7.py)（30 个）：<br>• 状态表完整；STATUS_CHECKED 的来源字段；<br>• 开盘涨停 3 种写法 → FILL_UNVERIFIED（保留 fwd_ret，exec_ret 为 NaN）；`open` 比 `high` 低 0.01 的边界；<br>• 可信来源下的一字板；不可信或缺失来源（4 种）；状态不完整；<br>• 停牌 / 限制 / 零量（4 种）；无状态列时的零量；<br>• 订单 FILLED（成交价、覆盖涨停判定）；盘口 NOT_FILLED；<br>• 证据校验失败（8 种）；证据未匹配 / 与状态矛盾；<br>• 组汇总的 exec 统计剔除 FILL_UNVERIFIED，报告中有相应说明；<br>• `exec_ret` 被禁止出现在特征表中 |
| 更新的既有测试 | T02 前缀不变性（`calendar_sha256` 随截断日历变化，改为单独断言）；T13（ELIGIBLE 需要可信来源，SYNTHETIC 来源 → UNVERIFIED）；T17 T+1 状态（改为新状态名）；WP-A schema（新增两个标记列） |

覆盖率：[coverage.txt](r7/coverage.txt) / [coverage.xml](r7/coverage.xml)，**TOTAL 91%（1788 条语句，未覆盖 164）**。分模块：

| 模块 | 覆盖率 |
|---|---|
| calendar_policy.py | 95% |
| event_study.py | 96% |
| cli.py | 95% |
| join.py | 95% |
| aggregate.py | 94% |
| schema.py | 89% |
| sessions.py | 88% |
| adapters.py | 84% |
| features.py | 79% |
| baselines.py | 66% |

## 5. SYNTHETIC_DEMO（`python run_demo.py`，无参数）

日志：[demo_run_log.txt](r7/demo_run_log.txt)（`exit_code=0`）；输出：[demo_outputs/](r7/demo_outputs/)（Parquet 未入库）。

- `study_context`：
  - `calendar_kind=SYNTHETIC_GENERATED`
  - `calendar_sha256=76b5b1da…55dd`
  - `calendar_source=mbv.adapters.generate_synthetic_market_bundle(seed=20261111, n_sessions=170)`
  - `research_grade=SYNTHETIC_DEMO_ONLY`
- T+1：模拟数据没有可信状态来源，因此 `TRADABILITY_UNVERIFIED_T1` 507 行、`PENDING_FUTURE_SESSION` 3 行；`execution_class` 为 FILL_UNVERIFIED 507 / NO_DATA 3。所有组的 `exec_effective_events = 0`，符合预期：模拟样本不计入可执行统计。
- 行数、特征状态、B0 事件数（EU 8 / ABU 1 / VU 1）、匹配对照（strict → INCONCLUSIVE）、Group E（p=0.339，`NOT_EVIDENCE_SYNTHETIC`）、bootstrap（9 个事件中 7 个可用）都与 R6 相同；`group_summary` 的假设收益列与 R6 逐值一致。结论仍为 `NO_RESEARCH_CONCLUSION`。

## 6. 哈希与冻结基线

| 文件 | SHA-256 |
|---|---|
| mbv/calendar_policy.py（新） | `725bfac76249fb36b43431ee11e767badd92c7f11cfd3267c585f1a292744b7f` |
| mbv/event_study.py | `f93a9ab6041832609835f158947ac8ec6dfa136101ac59911755a774840e374b` |
| mbv/cli.py | `3aa94020e9113f3f1e234f87552a2c82278f2320baae9275e12e5ebf3992621a` |
| mbv/join.py | `7a877d29b83a033279407b6f9217e1df595e0ce08607be19a8d659b415ed711d` |
| mbv/schema.py | `f0f2e0845763852fbcfbfc16fad1015a7da403322e95b059178f3fab952370c6` |
| aggregate / baselines / features / sessions / adapters | 与 R6 相同 |

- `git diff origin/master -- projects/tdx-volume-liquidity-residual/{indicator,selectors,verify}` 的结果为**空**。
- `reference/` 相对 R6 没有变化；T15 哈希断言通过（indicator `9913cced…`，selectors `31a00eba…` / `2cb07ba1…` / `99c46e67…`，verify `3dfba129…` / `bc647ac1…` / `ed224329…`）。

## 7. 复核命令

```bash
cd projects/tdx-volume-liquidity-residual/research/microburst_v0
python -m pytest -q tests -ra                                  # 期望 138 passed
python -m pytest --cov=mbv --cov-report=term-missing -q tests  # 期望 TOTAL 91%
python run_demo.py                                             # exit 0
```

## 8. 待复核方确认的问题

1. **`STATUS_CHECKED_EXECUTABLE` 是否计入“已确认可执行”**：本实现中，可信状态显示 T+1 未停牌、无限制、开盘未封涨停时，按开盘价计入 `exec_ret`（以 `exec_entry_basis=STATUS_CHECKED_T1_OPEN` 区分）。如复核方要求只有订单证据才算，可把该类移出 `EXECUTABLE_CLASSES`（只需改一处常量，测试会相应失败提示）。
2. **OOS 预热期**：特征管线允许使用 `sample_start` 之前的数据作为 20 日基线预热；事件研究的样本日期严格限制在窗口内。请确认这一做法是否符合预登记口径。
3. **可信来源的判定**目前仅检查 `tradability_status_source` 非空且不以 `SYNTHETIC` 开头；尚未与真实数据源白名单绑定（需要 G1 的真实数据）。
4. `--execution-evidence` 只校验结构和一致性，**不验证证据本身的真伪**（例如券商回单签名），需在真实数据阶段补充。
5. G1/G2/G3 维持原状态，需取得真实数据和独立验证证据后再评估。
