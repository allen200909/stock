# 威胁模型、许可证边界与研究局限 (`THREAT_MODEL.md` & `LIMITATIONS.md`)

## 1. 量化研究与工程威胁模型（Threat Model）

| 威胁类别 | 具体风险场景 | MBV V0.1 防护机制 | 对应测试 |
|---|---|---|---|
| **前视偏差 / 未来泄漏** | 使用全样本中位数或当日未收盘分钟更新历史基准；将未来收益列混入 T 日特征文件 | 严格按 `u < t` 已完成交易日构建 20 日同槽位滚动基准；T 日特征 Schema 禁止未来列 | T01, T02, T17 |
| **跨标的串联污染** | 多股票面板混合计算分钟中位数或 VLR 状态 | 所有基准、日内聚合与 B0 计算均严格按 `symbol` 隔离分组 | T03, T15 |
| **时间戳与时段错位** | 券商/行情商混用开盘时间戳（`09:30`）与收盘时间戳（`09:35`/`15:00`），或混入 `11:30–13:00` 午休伪 K 线 | `sessions.py` 强制校验会话边界与语义一致性，发现歧义立即 fail-closed | T04, T05, T06 |
| **脏数据与零基准伪信号** | 负成交量、OHLC 倒挂、重复时间戳、基准为 0 产生 `inf`、缺数据日被填为 `burst_count=0` | `schema.py` 严格拦截异常值；零基准置 `BASELINE_INVALID`；覆盖率 `<95%` 或零量日输出 `NaN` + 状态码 | T07, T08, T09, T14 |
| **样本选择与静默丢行** | 分钟数据缺失导致日线 B0 信号在 merge 时被内连接丢弃，或重复键导致样本翻倍 | `join_daily_vlr_mbv` 采用双边唯一键校验 + 左连接，完整保留全部 B0 日期并标注 `MINUTE_DATA_MISSING` | T12, T14 |
| **微观结构过度解读** | 将分钟 K 线实体方向 `(C-O)/(H-L)` 当成真实逐笔主买/主卖净流入 | 术语与报告强制限定为“K 线实体效率代理”，不作资金流因果宣称 | SPEC / T20 |
| **统计伪显著性** | 横截面同日触发重叠、RVOL 共线性或小样本对照组缺失下强行宣称有效 | 同日同 RVOL 桶匹配对照、组内因子置换负对照、样本不足标 `INCONCLUSIVE`、复用日历区块 Bootstrap | T18, T19, T20 |

## 2. 许可证与来源边界（License Provenance）
- `reference/third_party/Zeiierman_LTF_Volume_Microburst_Bubbles.pine` 为用户归档的第三方参考脚本，许可证为 **CC BY-NC-SA 4.0**。
- 本项目的 `mbv/` Python 引擎完全基于 `docs/完整开发计划书.md` 中的公开数学定义做 **Clean-room 独立实现**，未复制、转译或派生任何 Pine 源码、注释、绘图逻辑或独特函数结构。
- `reference/vlr_verify/` 为既有仓库冻结 VLR V2.1.2 Python 研究快照，仅以只读方式导入 `calculate(..., model="B0")` 与 `block_bootstrap(...)`，原文件字节级未改动。

## 3. 当前已知局限与未过门禁（Limitations & Open Gates）
1. **`G1 = BLOCKED_REAL_DATA`**：离线环境无经过核验的 QMT / PTrade 真实 A 股全市场历史 1m/5m 数据与点时退市/复权/涨跌停库；所有运行结果均为 `SYNTHETIC_DEMO`。
2. **`G2 = TDX_PARITY_NOT_VERIFIED`**：上游 `vlr.py` 的 B0 实现尚未完成真实通达信客户端全部 21 项输出逐 K 对拍（尤其是首根 K 线 `SMA(TR,14,1)` 初始化细节），联合研究状态保持 `PROVISIONAL_RESEARCH`。
3. **`G3 = NOT_EVALUATED_ON_REAL_OOS`**：未在真实点时无幸存者偏差样本及未暴露的前瞻样本上验证 H1/H2/H3，严禁用于任何实盘交易决策。
