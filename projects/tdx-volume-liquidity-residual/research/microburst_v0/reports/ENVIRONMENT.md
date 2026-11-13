# WP0 环境勘测与离线基线清点 (`ENVIRONMENT.md`)

## 1. 运行环境与依赖版本
- **操作系统**：Windows (win32, AMD64)
- **Python 版本**：`3.14.7` (`[MSC v.1944 64 bit (AMD64)]`)
- **核心库版本**：
  - `pandas`: `3.0.6`
  - `numpy`: `2.5.3`
  - `pytest`: `9.1.1`
  - `PyYAML`: `6.0.3`
  - `pyarrow`: 当前离线环境未预装（适配器已支持 `pyarrow`/`fastparquet` 自动检测，缺省时支持 CSV 与显式状态提示，满足离线零网络依赖可复现要求）。

## 2. 原始 WIP 原型现状评估（整改前 8 项核心结论）
1. `mbv/baselines.py` 直接对全表执行 `df.groupby(df['ts'].dt.time)['volume'].median()`，**严重违反过去窗口因果性（未来数据泄漏，T01/T02 失败）且跨股票混算（T03 失败）**，无 20 日滚动窗口与最少 15 日门槛（T09 缺失）。
2. `mbv/adapters.py` 忽略输入路径，从元旦 `2026-01-01 09:30` 连续生成 240 分钟随机序列，包含 `11:30–13:00` 午休 90 根非法 K 线（T04/T06 失败），且在 `pandas 3.0+` 下因旧频率别名 `'T'` 直接抛出 `ValueError: Invalid frequency: T` 崩溃。
3. `mbv/adapters.py` 中 `open/high/low/close` 彼此独立采样，违背 `low <= min(O,C) <= max(O,C) <= high`（T07 失败）。
4. `mbv/features.py` 仅判断 `relative_volume >= 2.5`，缺失实体效率门槛 `|E_{t,k}| >= 0.10`，且基准为 0 时产生 `inf` 伪爆量（T07 失败）。
5. `mbv/aggregate.py` 仅返回 `burst_count` 和 `burst_share` 两个键；无成交量或数据缺失时返回 `0` 而非 `NaN` + 状态码（T08 失败）；缺失 `peak_ratio`、`burst_dominance`、`burst_concentration`（含 `n=1` 特例）、`burst_direction_agreement`、覆盖率及日分钟量对账误差（T10/T11 缺失）。
6. `mbv/join.py` 未做双边 `(symbol, trade_date)` 唯一性校验，重复键会导致 B0 事件行膨胀（T14 失败），且未标记缺失分钟数据的 `feature_status`（T12 不完整）。
7. `mbv/schema.py` 仅为静态 `dataclass`，无时区、时间戳开/收盘语义转换（T05）、股/手单位换算、公司行为与可成交性状态字段验证（T13）。
8. 完全缺失只读 `vlr.calculate(..., model='B0')` 桥接（T15）、交易日历门禁（T16）、前瞻收益隔离（T17）、同日同 RVOL 对照匹配与负对照置换（T18）、区块 Bootstrap 对接（T19）以及 `SYNTHETIC_DEMO` CLI 与报告（T20）。

## 3. 只读参考快照与 SHA256 指纹核验
以下文件在开发与测试全过程中保持**严格只读**，未作任何修改，亦未混入 Apache-2.0 业务模块：

| 只读参考文件 | SHA256 | 许可与用途 |
|---|---|---|
| `reference/vlr_verify/vlr.py` | `3DFBA129C22282B3409A0D32F6781638B0699D8C1D2393E81A0CD8EC7B3F07B8` | 冻结 VLR V2.1.2 B0 只读调用 |
| `reference/vlr_verify/validation.py` | `BC647AC1E64753A1BC2AF15525A755B9162F646ACD99E299A475EE96CC5A12D3` | `vlr.py` 只读依赖 |
| `reference/vlr_verify/inference.py` | `ED2243298785C93755F2A5CF20E5F9D930B544CE2E6523F9703508A07732BEF1` | 日历区块 Bootstrap 只读复用 |
| `reference/third_party/NOTICE.md` | `A9E95D310B93AFDB14BA75DEF30F2A3CAF8B311767B39909D8A23DEB138AE3BB` | 第三方版权与边界声明 |
| `reference/third_party/Zeiierman_LTF_Volume_Microburst_Bubbles.pine` | `28E9657EE5F329FA76B737F59D49BFAEE1354F159137D76E1F889B64F1560125` | CC BY-NC-SA 4.0 概念参考（未移植源码） |
