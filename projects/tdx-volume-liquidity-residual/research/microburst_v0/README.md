# MBV — VLR × Microburst Validation Layer (V0.1)

> **Status: ENGINEERING HANDOFF ONLY** — no Python MBV research engine has yet been implemented or verified in this branch. Source code in `third_party/` is the user-provided Zeiierman Pine reference, **not** a developed MBV implementation.

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

## Current deliverables

| Item | Status |
|---|---|
| Research plan / RFC | Committed |
| Claude Code task brief | Committed |
| Original Pine script as reference | Archived, uncompiled / unverified |
| Python MBV engine, adapters, CLI | NOT IMPLEMENTED |
| T01–T20 tests and synthetic demo | NOT RUN / NOT IMPLEMENTED |
| Authentic data, TDX parity, OOS study | NOT VERIFIED |

No modification of the existing frozen B0 files is intended in this handoff.
