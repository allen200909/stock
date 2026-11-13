# MBV — VLR × Microburst Validation Layer (V0.1)

## 当前状态（R7，2026-11-13，分支 `feature/vlr-microburst-v0-r7`，未合并 master）

- 代码链路：Carbon R5（ZIP SHA-256 `10f9e12a…84991927`）→ R6（WP-A/B/C，`feature/vlr-microburst-v0-r6`）→ R7（设计决定：交易所日历策略、T+1 成交可行性分级）。
- **pytest 138 passed / 0 failed，覆盖率 91%；`python run_demo.py` exit 0（SYNTHETIC_DEMO）。** 证据见 [R7 设计决定实施报告](reports/R7_DESIGN_DECISIONS_REPORT.md) 与 [reports/r7/](reports/r7/)；R6 验收见 [R6_ACCEPTANCE_REPORT.md](reports/R6_ACCEPTANCE_REPORT.md)。
- 门禁：G1 **BLOCKED_REAL_DATA** · G2 **NOT_VERIFIED** · G3 **NOT_TESTED**（未变）。任何输出都不是 alpha 或交易证据。
- 研究模式（`mbv/calendar_policy.py`）：
  - `SYNTHETIC_DEMO`：允许固定生成的模拟日历（标注 `SYNTHETIC_GENERATED`）；特征管线未传日历时标注 `NONE_SYMBOL_OBSERVED_DATES`（仅限模拟）。
  - `EXPLORATORY_REAL_DATA`：必须提供交易所日历 + 来源记录（`kind=EXCHANGE`、`source`、`verified: true`、`verified_by`、与日历一致的 `calendar_sha256`）。
  - `CONFIRMATORY_OOS`：在上述基础上还需预登记记录（文档哈希核验、登记日早于样本起点、样本窗口在日历内、分析日期全部落在窗口内）。仅传入字符串不会获得正式标签；离线最高为 `CONFIRMATORY_OOS_CANDIDATE_PENDING_INDEPENDENT_REVIEW`。
  - 特征表带 `calendar_kind` / `calendar_sha256`，事件研究会核对它们与研究日历一致；正式模式不允许静默退回按证券行情日期滚动。20 日窗口、≥15 个正量样本规则不变。
- T+1 成交可行性：`LIMIT_UP + open>=high` 只作为保守排除（`OPEN_LIMIT_UP_FILL_UNVERIFIED_T1`），状态列只有在声明了非合成的 `tradability_status_source` 时才被信任；实际未成交/成交只能由订单或盘口证据（`--execution-evidence`）确认。`fwd_ret_*` 为假设开盘价收益（因子研究用），`exec_ret_*` 仅含已确认可执行样本，两者分开保存。

### 运行

```bash
python -m pytest -q tests -ra
python run_demo.py                                     # SYNTHETIC_DEMO，输出到 examples/demo_outputs/
python -m mbv.cli compute-features --minute m.csv --calendar cal.csv --out f.csv \
    --study-mode EXPLORATORY_REAL_DATA --calendar-provenance cal_provenance.json
python -m mbv.cli study --joined j.csv --calendar cal.csv --outdir out/ \
    --study-mode EXPLORATORY_REAL_DATA --calendar-provenance cal_provenance.json \
    [--execution-evidence evidence.csv] [--preregistration prereg.json  # CONFIRMATORY_OOS]
```

## Source reference and license

- [Third-party Pine reference](third_party/Zeiierman_LTF_Volume_Microburst_Bubbles.pine) — original user-supplied script; no changes to its calculation logic were made for this commit.
- [Source provenance, copyright and license boundaries](third_party/NOTICE.md).
- Original script's author: Zeiierman. Source: https://www.tradingview.com/script/Hdskv6Q5-LTF-Volume-Microburst-Bubbles-Zeiierman/
- This source is labeled **CC BY-NC-SA 4.0**, not Apache-2.0. It is separated for reference only. Do not import, vendor, translate or derive from the Pine source into the project implementation without checking licensing compatibility and permissions. A design independent of source expression is specified in the plan.

## 交付物状态

| 项目 | 状态 |
|---|---|
| 研究计划 / RFC、Claude Code 任务说明 | 已提交（历史文档） |
| 原始 Pine 脚本 | 仅作参考存档，未编译/未验证，未被移植 |
| Python MBV 引擎、适配器、CLI | R7：T01–T20 + R7 策略测试全部通过（仅代码级；需独立复核） |
| 真实数据、TDX 对拍、OOS 研究 | 未验证（G1/G2/G3） |

VLR V2.1.2 冻结基线（`indicator/`、`selectors/`、`verify/`）及 `reference/` 未修改。

## 历史记录（已过时，仅供追溯）

- [R5 → R6 交接书（2026-11-11）](AGENT_HANDOFF_R5_STATUS_AND_R6_PLAN_2026-11-11.md)：其中“本分支 `mbv/*.py` 为旧版 WIP”与“R5 7 passed / 2 failed、覆盖率 37%”的描述针对 R6 导入前的状态，**现已不适用**。
- [独立 QA 报告（2026-11-11）](QA_REPORT_INDEPENDENT_2026-11-11.md)：针对最初 Claude Code WIP 原型（G0 FAIL）的审计，所列缺陷已在 R5/R6 中处理并有对应测试。
- [VLR_Microburst_V0.1_ClaudeCode_Implementation_Plan.md](VLR_Microburst_V0.1_ClaudeCode_Implementation_Plan.md)、[Claude_Code_MBV_V0.1_Execution_Brief.md](Claude_Code_MBV_V0.1_Execution_Brief.md)：原始实施计划与任务说明。
