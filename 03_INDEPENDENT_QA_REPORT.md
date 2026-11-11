# MBV V0.1 既有 WIP 原型：独立 QA 报告（2026-11-11）

**结论：G0 FAIL / NOT ACCEPTED。** Claude Code 提交的是早期不完整原型，已收到的本地 ZIP 不能被当作可用于真实量化研究的合格实现。

## 原始交付、环境与可复现证据

- 原始压缩包：`original_delivery/MBV_V0.1_Deliverables.zip`；SHA256：`bc697479081f40a82b795f289099ee87d19a1af718a8edddb02edc8917441c2e`。
- 源文件：6 个 Python 实现、一个 pytest 烟测和开发日志。原始 `.pyc` 与缓存未作为任务源码使用。
- 既往独立运行环境：Python 3.13.5、pytest 9.0.2、pandas 2.2.3、numpy 2.3.5。仅一个 pytest 测试 PASS；总覆盖率曾为 12%。该运行不是全量验收。
- 本交接包另提供 `qa_known_defects_repro.py`，用于 **重现缺陷**，不能作为“通过了测试”的依据。

## P0：可以从提供的源代码直接确认或复现

| 问题 | 源码 | 现象与复核 |
|---|---|---|
| 未来数据泄漏，违反 T01/T02 | `mbv/baselines.py` | `groupby(ts.time).median()` 使用整段输入：09:30 量100，追加次日量10,000后早期基准变5,050，既未滞后也未使用20日窗口 |
| 跨股票污染，违反 T03 | `mbv/baselines.py` | 股票 A/B 相同 09:30 的成交量分别100/10,000，共用一个5,050基准 |
| 午休与时间戳无效，违反 T04/T06 | `mbv/adapters.py` | 自 2026-01-01 09:30 连续生成240分钟，含11:30–13:00午休90根，且元旦非正常A股交易日；忽略 filepath |
| 不满足 OHLC 验证，违反 T07 | `mbv/adapters.py` | O/H/L/C 独立随机，high可能低于close或open、low可能高于open或close |
| 缺少实体效率门槛 | `mbv/features.py` | 只看量比>=2.5，未验证 `abs((close-open)/(high-low)) >= 0.1`；O=C 的平K也被判 burst |
| 零基准出 `inf`，违反 T07 | `mbv/features.py` | 量比直接相除，未标注 `BASELINE_INVALID`，有可能形成虚假暴量 |
| 缺数被误标为无爆量，违反 T08 | `mbv/aggregate.py` | total_volume=0 时返回 `burst_share=0`，未以 `NO_VOLUME` / NaN 区分 |
| 重复键行数膨胀，违反 T14 | `mbv/join.py` | `(symbol,trade_date)` 重复时一行 B0 可 join 成两行，未 fail-closed |

## P1：必要模块缺失或只是占位实现

- `mbv/schema.py` 只有 dataclass，不做价格、日期、时区、频率、单位、唯一键及可用日历验证。
- `mbv/baselines.py` 不支持历史20个完整交易日中位数/最少15天、正量、证券与时间槽位隔离。
- `mbv/aggregate.py` 只产生 `burst_count`、`burst_share`，缺少 `peak_ratio`, `burst_dominance`, `burst_concentration`, `burst_direction_agreement`、覆盖率、对账和 `feature_status`。
- `mbv/join.py` 的普通 left merge 在一对一夹具中可保留 B0 行，但缺失 MBV 质量状态与唯一键校验，不能算完成 T12。
- 无真实 CSV/Parquet 适配器、QMT/PTADE 接口契约、确定性有效交易日样本、B0 只读计算对接、事件研究、条件匹配、bootstrap 研究 CLI 和合成报告。

## 原定 T01–T20 验收矩阵（对现有 WIP 的结果）

| 测试 | 既有状态 | 理由 |
|---|---|---|
| T01 | FAIL | 未来分钟/交易日改变历史基准 |
| T02 | FAIL | 前缀不变性被整段 median 破坏 |
| T03 | FAIL | 跨证券共享基准 |
| T04 | FAIL | 模拟午休有错误K线 |
| T05 | NOT IMPLEMENTED | 无开盘/结束时间戳转换和歧义检测 |
| T06 | FAIL | 1m/5m正常会话槽位处理不满足 |
| T07 | FAIL | OHLC随机无效、零基准无穷、缺数据检查不全 |
| T08 | NOT IMPLEMENTED | 不足95%覆盖率门禁不存在 |
| T09 | NOT IMPLEMENTED | 最少15历史同槽位交易日门禁不存在 |
| T10 | NOT IMPLEMENTED | 无事件/单事件/对冲方向、HHI未实现 |
| T11 | NOT IMPLEMENTED | 无集中爆发vs均匀放量构造样本测试 |
| T12 | PARTIAL | 左连接基本保留 B0，缺失标记未实现 |
| T13 | NOT IMPLEMENTED | 无公司行为、停牌、涨跌停标记 |
| T14 | FAIL | 重复键使 B0 行数膨胀 |
| T15 | NOT RUN | 未真正调用 B0 只读 API / 回归对照 |
| T16 | NOT IMPLEMENTED | 无真实交易日历执行门禁 |
| T17 | NOT IMPLEMENTED | 无 forward-return 标签隔离 |
| T18 | NOT IMPLEMENTED | 无匹配对照组 / INCONCLUSIVE 处理 |
| T19 | NOT IMPLEMENTED | 无区块 bootstrap 对接 |
| T20 | NOT IMPLEMENTED | 无完整 `SYNTHETIC_DEMO` 研究输出 |

仅一个额外的 `test_burst_detection` 简单烟测曾通过，不属于证明 T01–T20 完整通过的证据。

## 门禁及整改后验收原则

- **G0 FAIL**：先修上述错误，补完 T01–T20 的正向测试与 CLI / 合成演示，并且真正运行全部测试。
- **G1 BLOCKED_REAL_DATA**：没有经过核验的本地 QMT/PTADE 分钟数据、覆盖率和分钟-日线成交量对账。
- **G2 TDX_PARITY_NOT_VERIFIED**：原 VLR Python B0 仍未取得真实通达信21序列逐K对拍。
- **G3 NOT TESTED**：没有点时有效真实样本、未来收益、条件对照和预注册OOS结果。

达到 G0 并不等于通过 G1–G3。请在后续报告中明确区分“软件/合成测试PASS”与“实证研究PASS”，严禁未验证模型直接用于实盘交易。
