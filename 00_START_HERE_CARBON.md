# MBV V0.1 — Carbon / DSH 完全离线任务交付包

**用途**：把本 ZIP 直接交给 DSH 中的 Carbon 执行；**不需要连接 GitHub、不需要克隆仓库，也不要求推送或创建 PR**。

## 从哪里开始

1. 解压本包到可写目录，不要覆盖已有生产项目。
2. **先阅读 `01_CARBON_OFFLINE_EXECUTION_PROMPT.md`**，其后依次阅读 `docs/完整开发计划书.md`、`03_INDEPENDENT_QA_REPORT.md` 和 `02_TASK_INDEX_AND_ACCEPTANCE.md`。
3. 修改 `project/` 中的 **现有 WIP 源码**，按计划补完缺失模块。原始交付 ZIP 保存在 `original_delivery/` 仅用于溯源。
4. 如需只读调用 VLR B0：`reference/vlr_verify/` 已提供 Python 原始实现 `vlr.py` 及依赖的 `validation.py`；不要编辑或把该代码与 MBV 直接合并。`reference/vlr_verify/inference.py` 供事件分析参考。
5. 完成后在本地运行全部测试，将 **实际终端输出**、QA 报告、全部源码、运行说明和输入样例打成一个新 ZIP，直接回传用户，不要等待 GitHub 联通。

## 包内主要内容

| 路径 | 内容 | 性质 |
|---|---|---|
| `01_CARBON_OFFLINE_EXECUTION_PROMPT.md` | Carbon 专用离线执行指令 | **最高优先级的工作流说明** |
| `docs/完整开发计划书.md` | 438 行 V0.1 RFC、公式、WP0–WP4、T01–T20 | 完整任务规格 |
| `docs/原始ClaudeCode任务说明.md` | 原始执行要求 | 历史说明；涉及 GitHub 的要求由离线指令覆盖 |
| `03_INDEPENDENT_QA_REPORT.md` | 先前独立审查结果、阻断问题 | 待整改问题清单 |
| `02_TASK_INDEX_AND_ACCEPTANCE.md` | 测试矩阵和交付验收细则 | 可逐项勾核 |
| `project/mbv/*.py`, `project/tests/` | Claude Code 已交付的 WIP 代码和1个烟测 | **未验收，不可视为完成品** |
| `reference/vlr_verify/` | 从现有 VLR 项目取出的只读 B0 研究代码 | 辅助离线适配；原 B0 未经真实 TDX 对拍 |
| `reference/third_party/` | 用户提供的 Zeiierman Pine v6 原脚本及版权声明 | 第三方 CC BY-NC-SA 4.0；仅参考、禁止直接改编混入 |
| `qa_known_defects_repro.py` | 已知缺陷重现脚本 | **故意检查错误是否存在，不是正向验收测试** |
| `original_delivery/MBV_V0.1_Deliverables.zip` | Claude Code 原始小 ZIP | 追溯原始提交 |
| `SHA256SUMS.txt` | 文件哈希列表 | 完整性核对 |

## 现状与红线

- **已知 G0 = FAIL**：未来数据泄漏、跨证券基准污染、零基准 `inf`、合成数据午休和 OHLC 错误、缺少实体效率、join 键重复放大，均需修复。
- 目前 **仅 1 个基本单元测试通过**；不代表 T01–T20 通过。
- 真实 QMT/PTADE 分钟数据、真实通达信逐K对拍、OOS 收益验证均未获得。禁止虚构或宣布通过。
- VLR V2.1.2 冻结基线只读；不生成实盘买卖指令。
- 所有 Python 新文件、测试及文档可离线写入 `project/`；所有修改应当可复现。
- 离线任务对**网络受限没有阻断理由**；缺少真实数据的部分按 `BLOCKED_REAL_DATA` 如实交付软件与合成验证。

**本包是任务交接与参考源代码快照，不是已经完成的 MBV 模型。**
