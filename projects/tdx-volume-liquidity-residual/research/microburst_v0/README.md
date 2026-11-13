# MBV — VLR × Microburst Validation Layer (V0.1)

## R6 状态（2026-11-12，分支 `feature/vlr-microburst-v0-r6`，未合并 master）

- 源码基线：Carbon R5 ZIP（SHA-256 `10f9e12a…84991927`，28 条目）原样导入后增量完成 WP-A → WP-B → WP-C。
- **pytest 90 passed / 0 failed，覆盖率 89%；`python run_demo.py` exit 0，输出非空 SYNTHETIC_DEMO 结果。T01–T20 自动化断言全部 PASS。**
- 门禁：G1 **BLOCKED_REAL_DATA** · G2 **NOT_VERIFIED** · G3 **NOT_TESTED**。不得据此声称 alpha 或合并 master。
- 详见 [R6 验收报告](reports/R6_ACCEPTANCE_REPORT.md)（基线复现、改动、T 编号→测试映射、覆盖率、哈希、复核命令）及原始日志 [reports/r6/](reports/r6/)。
- 以下 R5 / 更早段落保留为历史记录（其中“旧版 WIP”警告指 R6 导入前的 GitHub 源码）。

## 新 Agent 接手入口（2026-11-11，R5 → R6）

- [R5 已完成内容、剩余缺陷、T01–T20 矩阵、R6 执行步骤及验收门槛](AGENT_HANDOFF_R5_STATUS_AND_R6_PLAN_2026-11-11.md)
- **重要版本说明：本分支当前的 `mbv/*.py` 为旧版 WIP，不是 Carbon R5 源码。** 新 Agent 必须同时获取用户提供的 `MBV_V0.1_Carbon_Completed_R5.zip`（SHA-256: `10f9e12ae4f0ad70f561ffd626a2dee2fd991ab845971b6923613aee84991927`），在 R5 基础上续作。
- 独立复验：R5 为 **7 passed / 2 failed**、覆盖率 37%、`python run_demo.py` 失败。G0 未过，不得合并 master。


> **Status: UNVERIFIED WIP / G0 FAILED (independent audit 2026-11-11).** The Claude Code ZIP's six small Python prototype modules and one smoke test have been archived on this development branch. They are **not a completed MBV V0.1**, do not pass T01–T20 and must not be treated as validated market research. See [independent QA report](QA_REPORT_INDEPENDENT_2026-11-11.md). Source code in `third_party/` remains the separate user-provided Zeiierman Pine reference.

## Claude Code handoff

1. Read [VLR_Microburst_V0.1_ClaudeCode_Implementation_Plan.md](VLR_Microburst_V0.1_ClaudeCode_Implementation_Plan.md) in full.
2. Execute [Claude_Code_MBV_V0.1_Execution_Brief.md](Claude_Code_MBV_V0.1_Execution_Brief.md).
3. Implement the independent Python module in this directory on `feature/vlr-microburst-v0`, starting WP0 -> WP1 -> WP2 -> WP4. WP3 Pine visualization is optional.
4. Reuse the existing B0 read-only API from `../../verify/vlr.py`; preserve VLR V2.1.2 frozen indicator and selectors, and never claim full authentic TongDaXin parity or OOS alpha without evidence.

## Source reference and license

- [Third-party Pine reference](third_party/Zeiierman_LTF_Volume_Microburst_Bubbles.pine) — original user-supplied script; no changes to its calculation logic were made for this commit.
- [Source provenance, copyright and license boundaries](third_party/NOTICE.md).
- Original script's author: Zeiierman. Source: https://www.tradingview.com/script/Hdskv6Q5-LTF-Volume-Microburst-Bubbles-Zeiierman/
- This source is labeled **CC BY-NC-SA 4.0**, not Apache-2.0. It is separated for reference only. Do not import, vendor, translate or derive from the Pine source into the project implementation without checking licensing compatibility and permissions. A design independent of source expression is specified in the plan.

## Independent QA status

- [Audit of Claude Code WIP source, reproduced failures, T01–T20 status and remediation](QA_REPORT_INDEPENDENT_2026-11-11.md)
- Only one simple pytest smoke test passes. Historical baseline look-ahead, cross-symbol contamination, A-share session handling, OHLC validation, missing-value gating and join cardinality are **known defects**.
- Keep VLR V2.1.2 frozen. G0 is **FAIL**; G1–G3 are unverified/blocked. Do not merge or use for production signals.

## Current deliverables

| Item | Status |
|---|---|
| Research plan / RFC | Committed |
| Claude Code task brief | Committed |
| Original Pine script as reference | Archived, uncompiled / unverified |
| Python MBV engine, adapters, CLI | Six Python WIP prototype files received; engine/CLI incomplete and unvalidated |
| T01–T20 tests and synthetic demo | One smoke test passed; T01–T20 not passed; see audit |
| Authentic data, TDX parity, OOS study | NOT VERIFIED |

No modification of the existing frozen B0 files is intended in this handoff.
