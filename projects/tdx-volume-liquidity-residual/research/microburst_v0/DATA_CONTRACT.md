# 数据契约规范 (`DATA_CONTRACT.md`)

## 1. 分钟 K 线契约（Minute Bars）
必填列：`symbol, ts, open, high, low, close, volume`；可选列：`amount`。

- **`symbol`**：带交易所后缀的标准代码（如 `600000.SH`, `000001.SZ`），禁止缺失或混用裸数字代码而不声明映射。
- **`ts`**：规范化到 `Asia/Shanghai` 的 **K 线开始时间（`bar_start`）**。
  - 若上游数据源使用收盘时间戳（`bar_end`，如 5 分钟首根标为 `09:35`、末根标为 `11:30` / `15:00`），必须在配置或适配器参数中显式声明 `timestamp_semantics="bar_end"`，由 `normalize_bar_timestamps()` 统一平移至 `bar_start`（`09:30` .. `11:25`, `13:00` .. `14:55`）。
  - 若声明 `bar_start` 却出现 `11:30` 或 `15:00`，或声明 `bar_end` 却出现 `09:30` 或 `13:00`，视为**语义歧义/越界，立即 fail-closed 报错**（满足 T05）。
  - `11:30 < ts < 13:00` 午间休市或盘前盘后非法槽位一律拒绝或按异常标记（满足 T04）。
- **唯一性与排序**：`(symbol, ts)` 严格唯一，重复时间戳直接抛出 `DataContractError`（满足 T07/T14）。
- **价格与成交量边界**：
  - `open, high, low, close > 0` 且有限；严格满足 `low <= min(open, close) <= max(open, close) <= high`（允许 `high == low` 一字板/平盘）。
  - `volume >= 0` 且有限；负成交量、NaN、Inf 直接拒绝（满足 T07）。
  - 单位统一：`volume_unit="share"`（股）或 `"lot_100"`（手，适配器乘以 100 转为股）；未知单位直接拒绝。
- **元数据溯源（Provenance）**：每次载入生成 `DatasetMetadata`，记录 `source`, `source_version`, `frequency`, `timezone`, `timestamp_semantics`, `volume_unit`, `amount_unit`, `adjustment`, `ingestion_time`, `source_hash`。

## 2. 日线与点时状态契约（Daily Bars & Point-in-Time Flags）
必填列：`symbol, trade_date, open, high, low, close, volume`；可选列：`amount, suspended, st_flag, board, listing_age_sessions, price_limit_status, corp_action_flag`。

- **`trade_date`**：无时区规范化交易日（`YYYY-MM-DD`），同 `(symbol, trade_date)` 严格唯一（重复键 fail-closed，满足 T14）。
- **企业行为与可成交性分离（满足 T13）**：
  - 状态列若未提供，可成交性标记为 `TRADABILITY_UNVERIFIED`（绝不默认伪造 `False` 声称可成交）。
  - 一字板（`high == low` 或 `price_limit_status` 涨跌停封死）、除权日（`corp_action_flag`）、ST、停牌恢复首日均保留在特征与左连接表中，同时通过 `data_risk_flags` 与 `execution_eligibility` 单独标注。

## 3. 交易日历契约（Trading Calendar）
- 正式事件收益（T+1 起 1/3/5/10/20 交易日）与区块 Bootstrap 研究**必须显式传入有序唯一的交易日历**。
- 未提供交易日历时拒绝运行事件收益/执行研究（满足 T16）；合成单元测试或 `SYNTHETIC_DEMO` 必须显式传入合成交易日历并在报告中标注 `SYNTHETIC_CALENDAR`。
- T 日特征输出文件严禁包含任何 `fwd_ret_*`、`mfe_*`、`mae_*` 等未来收益列（满足 T17）。
