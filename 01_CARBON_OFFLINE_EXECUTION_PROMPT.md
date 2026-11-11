# 给 DSH / Carbon 的执行指令 —— MBV V0.1 离线整改与完整开发

你是此任务的 Python 量化研究工程师和本地 QA 实施者。用户已通过离线 ZIP 提供全部**可用**任务材料。**GitHub 无法连接是已知环境限制，不要尝试反复 clone/push、不要以此作为停止工作的理由。**

## 优先级与权限

1. 优先执行此文件中的**离线工作方式**。完整科学/算法/测试要求以 `docs/完整开发计划书.md` 为准，已知缺陷以 `03_INDEPENDENT_QA_REPORT.md` 为准。
2. 原始执行说明若要求创建 GitHub 分支、远程提交、PR、远端回传等，在本次任务中**一律替换为本地文件交付和 ZIP 回传**；其余工程要求保持有效。
3. 工作范围限于压缩包中的 `project/` 目录。`reference/vlr_verify/`、`reference/third_party/`、`original_delivery/` 全部只读，禁止修改冻结 B0 及第三方 Pine。
4. 如当前 DSH 工作区已有用户修改，先备份并在局部工作目录实现，不覆盖用户已有成果。无须获得额外许可即可完成独立软件代码与测试；不访问私人行情数据或进行交易。

## 立即开始

- 首先检查 `project/mbv/` 六个现有源码文件与 `project/tests/test_features.py` 的具体实现，报告 6–12 行现状评估。
- 运行 `python -m pytest -q`（项目根目录、安装所需依赖后），记录真实输出。运行 `python qa_known_defects_repro.py` 以确认之前的错误（**它通过并不代表模型合格**）。
- 对照 `03_INDEPENDENT_QA_REPORT.md`，先修 P0：**未来数据参与历史中位数、证券污染、分钟交易日历与 OHLC 无效、成交量为0/缺数据、实体效率缺失、join 键重复、覆盖率与状态缺失**。
- 不要停留在修复七项；按原计划完整实现 WP0→WP1→WP2→WP4。WP3 Pine 展示是选做，不能用 Pine 图形代替 Python 完整验收。
- 历史分钟基准必须按 `(symbol, minute_slot)` 和**之前已完成的交易日**，采用滚动20日中位数、最少15个有效历史交易日；不能将当日或未来日带入。
- 精确支持上海市场午休、时间戳开盘/收盘语义、1分钟/5分钟数据规则、成交单位（股/手）、成交额单位、交易日历、每日覆盖率与数据质量门禁。分钟OHLCV只是一种方向代理，不等于逐笔资金净流入。
- 计算每日报告规定的 `burst_count`, `burst_share`, `peak_ratio`, `burst_dominance`, `burst_concentration`, `burst_direction_agreement`, `valid_slot_coverage`, `baseline_slot_coverage`, `vol_recon_error`, `feature_status`。一个事件 n=1 的集中度特殊定义与缺数据 NaN 状态必须实现。
- 左连接 B0+MBV，唯一键 `(symbol, trade_date)` 双边强校验。可从 `reference/vlr_verify/vlr.py` 通过只读导入 计算 B0，不得修改 B0 逻辑；`reference/vlr_verify/validation.py` 是它的依赖。
- 提供 CSV/Parquet 规范化适配器、明确数据契约和可复现 CLI；用确定性合成数据运行演示，报告标签必须为 `SYNTHETIC_DEMO`。
- 条件分组对比 VLR-only / MBV-only / VLR+MBV 以及日期、RVOL 匹配控制与 1/3/5/10/20 交易日事件研究；缺少真实收益或交易日历时只做合成演示，不编造绩效。

## 单测和验收硬门槛

- T01–T20 **逐项运行且全部 PASS** 才能宣布本地 G0 完成；不得以已有的 1 条 smoke test 抵扣 T01。
- 必须测试：历史前缀不变、跨证券不串、午休、时间戳语义、1m/5m 正常槽位、无效 OHLC、零基准、缺少历史、缺分钟、单事件/无事件方向与 HHI、成交量分布差异、日线缺分钟保留、重复键拒绝、执行门禁、收益未来列隔离、对照组无候选拒绝、bootstrap、真实与合成标签分离。
- 原 VLR B0 代码只读；添加兼容/不变性测试，确保 B0 输出不被重写。
- 不允许随意把既有代码占位符、未运行测试或缺数据的状态写成 PASS。

## 完成后必须回传的 ZIP 结构

将以下内容放入 **`MBV_V0.1_Carbon_Completed.zip`**（普通 ZIP，无 Git 依赖）交给用户：

```
MBV_V0.1_Carbon_Completed/
  README.md                    # 一条命令启动演示、环境依赖和用法
  mbv/                         # 所有 Python 源码
  tests/                       # 全部 T01-T20 测试
  data_adapters/               # CSV/Parquet/QMT/PTADE scaffold（有则含）
  config/                      # 固定默认参数与输入 contract
  examples/                    # 合成输入及生成脚本（无真实敏感数据）
  reports/QA_REPORT.md         # 真实运行命令、测试通过数、逐项状态、环境
  reports/REVIEW_REQUEST.md    # 需要独立审阅的公式/数据问题与未过 Gate
  reports/test_output.txt      # 实际 stdout/stderr，不能手写“通过”
  reports/CHANGELOG.md         # 对原 WIP 的修复与新增工作说明
  requirements.txt
  run_demo.py 或 cli.py
```

如果某项需要真实数据或实机通达信验证，保留 `BLOCKED_REAL_DATA` / `TDX_PARITY_NOT_VERIFIED` / `PROVISIONAL_RESEARCH` 等准确状态，并报告依赖缺口。即使 G1–G3 缺真实数据，**G0 独立软件研发仍须完成**。

**禁止**：依赖可用 GitHub 才执行、凭空写测试结果、以未验证结果宣传 alpha、修改第三方 Pine 许可文件、直接拿老项目的 VLR 指标当作已被 TDX 官方对拍确认。
