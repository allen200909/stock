# Changelog

## V2.1.2

- 将 RVVAC 调整为 1.20。
- 将 RVTH 调整为 1.50。
- 将方向权重参数化为 WDR/WDB/WCV。
- 对 DIR 权重做自动归一化。
- 保留 RHO。
- 增加 R2RAW = RHO²。
- 增加 R2POS = max(RHO,0)²。
- 增加强扩事件活跃度分层：QUIET / WARMUP / ACTIVE / HIGHACT / LONGACT / HOT。
- 增加三日强扩选股。
- 增加 60 日至少 3 次且近 10 日至少 1 次强扩选股。
- 增加基于活跃度分层的强扩选股。

## V2.1.1

- 将 BETA 改名 REGK，避免与通达信内置函数冲突。
- ALPHA 同步改名 REGB。

## V2.1

- 基准、OLS 与残差标准化改为滞后结构。
- 加入训练样本 Winsorize。
- 增加 DIR 三因子。
- 区分真空、强扩、吸收。
- 增加事件去重与充分预热。
