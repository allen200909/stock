# Changelog

## Repository hardening — 2026-10-13

- 冻结 V2.1.2 核心指标为 Baseline，不因审查意见直接改写历史基线。
- README 补充残差异方差、巨量截尾、收盘确认、复权与 A 股可成交性的已知限制。
- 明确“训练样本上限截尾”而非分位数 Winsorization。
- 明确 EXPECT 使用 RVFIT，修正文档中“当前检测完全保留原始值”的过度表述。
- 增加预注册验证协议 `docs/validation-protocol.md`。
- 增加 A 股执行层规范 `docs/a-share-execution-layer.md`。
- 增加审查响应与 V2.2 challenger 路线图。
- 增加 Python baseline 复刻与前缀不变性测试骨架。
- 活跃度分层增加 FADING / OTHER，补全状态空间；默认 XG 仍为 ACTIVE OR HIGHACT。
- 新建 `v2.2-experimental` 分支，用于 JUMBO、log-linear、conditional-scale 和 AMOUNT challenger。

## V2.1.2

- 将 RVVAC 调整为 1.20。
- 将 RVTH 调整为 1.50。
- 将方向权重参数化为 WDR/WDB/WCV。
- 对 DIR 权重做自动归一化。
- 保留 RHO。
- 增加 R2RAW = RHO²。
- 增加 R2POS = max(RHO,0)²。
- 增加强扩事件活跃度分层。
- 增加三日强扩选股。
- 增加 60 日至少 3 次且近 10 日至少 1 次强扩选股。

## V2.1.1

- 将 BETA 改名 REGK，避免与通达信内置函数冲突。
- ALPHA 同步改名 REGB。

## V2.1

- 基准、OLS 与残差标准化改为滞后结构。
- 加入训练样本上限截尾。
- 增加 DIR 三因子。
- 区分真空、强扩、吸收。
- 增加事件去重与充分预热。
