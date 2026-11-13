# Claude Code 执行任务｜VLR × Microburst V0.1

请阅读同目录的 `VLR_Microburst_V0.1_ClaudeCode_Implementation_Plan.md`，将其视为完整任务规格，并直接开展工程实现。

**仓库**：`allen200909/stock`

**工作目录**：`projects/tdx-volume-liquidity-residual/research/microburst_v0/`

**优先级**：WP0 → WP1 → WP2 → WP4；WP3 的 Pine v6 移植只是可选研究，不得替代 Python 验收。

**硬约束**：

1. VLR V2.1.2 为 Frozen Baseline；禁止更改稳定版 TDX 指标、3 个现有选股器和 `verify/vlr.py` 的 B0 算法。
2. 另建 `feature/vlr-microburst-v0` 独立分支；先检查当前 git 工作区，保护已有未提交改动。
3. 与旧 B0 仅通过只读 API 连接；分钟 Microburst 特征分开计算，不能反向修改 B0 事件。
4. 采用同分钟槽位、过去交易日的滞后成交量基准。严禁未来数据泄漏；严禁把分钟行情中的K线方向当作真实主动买卖订单流。
5. QMT/PTADE 无数据时仍须交付可运行 CSV/Parquet 输入、合成样本、单测、CLI 和报告模板；绝不伪造历史绩效。
6. 保持来源许可可追溯：Zeiierman 原脚本为 CC BY-NC-SA 4.0，仅以思想为参考，禁止直接复制源码。
7. 优先完成 T01–T20 测试，`git diff --check`，基线项目原测试；无真实 TDX 导出时保留 `TDX_PARITY_NOT_VERIFIED`。
8. 交付 `QA_REPORT.md`、`REVIEW_REQUEST.md`、结果状态与所有未达成 Gate。禁止擅自合并 master 或宣称实盘可用。

请先报告仓库真实代码结构与本文的差异，再直接实施。所有结果必须标注 `SYNTHETIC_DEMO` / `PROVISIONAL_RESEARCH` / `CONFIRMATORY_OOS` 中的适用状态。完成后提供实际变更文件清单、验证命令与真实测试输出，并列出下一轮人工验收需要的数据。