# MBV — VLR × Microburst Validation Layer (V0.1)

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
