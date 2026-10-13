# 通达信量价流动性残差模型

> Volume-Liquidity Residual Model for TongDaXin (TDX)

## 项目状态

当前稳定基线：**V2.1.2（Frozen Baseline）**

V2.1.2 的核心公式从 2026-10-13 起冻结，用于后续 challenger 模型的公平 A/B 比较。未经预注册验证、通达信逐 K 对拍和 OOS 检验，不直接替换基线。

实验方向放在独立分支：`v2.2-experimental`。

## 项目定位

本项目研究“成交量条件下的价格冲击异常”：

- 用历史相对成交量解释正常真实波幅；
- 当前 K 线不参与自己的基准、滚动回归和残差标准化；
- 正残差表示价格冲击高于模型预期；
- 负残差 + 明显放量表示大量成交未形成应有价格位移，作为吸收候选；
- 强扩事件进一步用 60/20/10 日窗口做活跃度分层，而不是简单认为次数越多越好。

> 注意：V2.1.2 使用**全局历史残差尺度**做 Z 标准化，并非严格的条件异方差模型。审查样本显示残差离散度会随 RVOL 增大，因此“当前量能条件下异常”是研究假设而非已经完成验证的统计结论。V2.2 challenger 专门处理这个问题。

## 核心信号

| 信号 | 条件摘要 | 解释 |
|---|---|---|
| 真空↑ / 真空↓ | Z > +1.5，方向明确，RVOL < 1.20 | 非明显放量却出现异常价格冲击 |
| 强扩↑ / 强扩↓ | Z > +1.5，方向明确，RVOL >= 1.20 | 价格冲击显著高于基线模型预期 |
| 吸收多 / 吸收空 | Z < -1.5，RVOL > 1.50，DIR 与 CLV 同向 | 大量成交未形成应有位移，观察承接/压制 |

A 股只做多场景中，向下三类信号主要用于风险识别、减仓/退出研究，不作为做空指令。

## V2.1.2 关键设计

1. **滞后基准**：ATR、成交量基准只使用前一根 K 线以前的数据。
2. **样本外检测**：当前 K 线不参与当前滚动 OLS。
3. **滞后残差标准化**：当前残差不参与自己的均值和标准差。
4. **训练样本上限截尾**：RVOL/MOV 的训练值采用固定上限截尾（不是分位数 Winsorization）。
5. **当前预测口径**：EXPECT 使用截尾后的 RVFIT；当前 MOV、RVRAW 阈值判断保留原值。RVRAW>RVCAP 的巨量区因此属于已知模型风险区。
6. **正斜率约束**：量价正常关系的 OLS 斜率约束为非负。
7. **R²双指标**：
   - R2RAW = RHO²，保留正负相关的原始线性强度；
   - R2POS = max(RHO,0)²，反映符合正斜率假设的有效关系强度。
8. **方向三因子**：DR + DB + CLV，权重可调并自动归一化。
9. **量能梯度**：RVVAC=1.20；RVTH=1.50。
10. **事件去重**：COOL=3。
11. **活跃度分层**：QUIET / WARMUP / ACTIVE / HIGHACT / LONGACT / HOT / FADING / OTHER。

## 已知限制

### 1. 残差异方差

V2.1.2 的 Z 使用统一残差标准差。量能越高时残差可能越分散，因此正负尾部触发率可能随 RVOL 改变。

### 2. 巨量区截尾

`RVFIT=MIN(RVRAW,RVCAP)`。当 RVRAW>3 时，预测端不再继续增加量能输入，可能系统性低估巨量日应有波幅。V2.2 将测试：
- JUMBO 独立 regime；
- log-linear；
- log-linear + conditional scale。

### 3. A 股可成交性

原始因子可以识别一字板/涨停等真实的流动性事件，但**因子成立不等于可成交**。交易研究必须另加执行层：ST、涨跌停可成交性、上市天数、停复牌和成交额门槛等。

### 4. 收盘确认

当期 H/L/C/VOL 在盘中尚未完成，信号可能变化。当前版本规定：
- **只使用收盘确认信号**；
- 回测统一按 T 日收盘确认、T+1 执行。

### 5. 复权与公司行为

研究和回测必须明确价格复权、除权除息、送转后的量能口径。不得混用不一致口径。

## 目录

```text
indicator/
  volume_liquidity_residual_v2.1.2.tdx

selectors/
  strong_expansion_3d.tdx
  strong_expansion_60d3_recent10.tdx
  strong_expansion_activity_layered.tdx

docs/
  model-notes.md
  validation-protocol.md
  a-share-execution-layer.md
  review-response-2026-10-13.md

verify/
  README.md
  vlr.py
  prefix_invariance.py

CHANGELOG.md
```

## 默认参数

```text
N       = 60
ATRN    = 14
VOLN    = 20
ZTH     = 1.50
RVVAC   = 1.20
RVTH    = 1.50
RVCAP   = 3.00
MVCAP   = 4.00
DTH     = 0.25
ATH     = 0.10
CTH     = 0.10
COOL    = 3

WDR     = 0.50
WDB     = 0.25
WCV     = 0.25
```

## 强扩活跃度分层

- **QUIET**：60 日 0–1 次，且非 HOT
- **WARMUP**：60 日 2 次、10 日至少 1 次，且非 HOT
- **ACTIVE**：60 日 3–4 次、10 日 1–2 次，且非 HOT
- **HIGHACT**：60 日 5–6 次、10 日 1–2 次，且非 HOT
- **LONGACT**：60 日 >=7 次，近期节奏合理，且非 HOT
- **HOT**：10 日 >=3 次，或 20 日 >=4 次
- **FADING**：60 日至少 2 次，但近 10 日为 0，且非 HOT
- **OTHER**：其余未被上述状态覆盖的组合

默认分层选股仍使用：

```text
XG:ACTIVE OR HIGHACT;
```

## 验证原则

正式研究前先阅读 `docs/validation-protocol.md`。核心原则：

1. 先冻结参数和数据口径，再看结果；
2. Python 复刻必须先与通达信逐 K 对拍；
3. T 日收盘确认，T+1 执行；
4. 对照组必须控制日期与 RVOL，避免把单纯“放量效应”误认为 residual alpha；
5. 报告 1/3/5/10/20 日 forward return、MFE、MAE、胜率、置信区间；
6. 参数只在训练段确定，OOS 段封存；
7. 新模型只有在 OOS、成本和稳定性上优于基线，才允许升级稳定版。

## 免责声明

本项目仅用于量化研究、指标实验和个人学习，不构成任何投资建议。历史统计不能保证未来表现。


## 2026-10-13 Verification Infrastructure

The frozen V2.1.2 indicator remains unchanged. The `verify/` directory now
provides a common Python research interface for B0/E1–E4 with:

- six signal event types, three selectors and eight activity states;
- prefix-invariance and partition tests (synthetic data);
- an explicit barwise TongDaXin export comparator;
- a fail-closed A-share execution research table with next-session
  `UNFILLED` vs `ELIGIBLE_FOR_FILL_CHECK` distinctions;
- a GitHub Actions synthetic-test workflow.

E3's experimental TongDaXin formula has an explicit three-stage warm-up.
Actual TongDaXin parity and an OOS event study have **not yet been completed**.
Details and run commands: [verify/README.md](verify/README.md).

**Research-data caveat:** the initial 50-stock analysis already inspected
2021–2026 residual distributions, so this period cannot be described as a
fully untouched model-design holdout. It remains possible to use its previously
unexamined return outcomes for a carefully disclosed performance evaluation,
but any eventual strategy claim needs an additional genuinely untouched
confirmation sample.

优化执行记录与验收边界见 [优化建议与验收书](docs/optimization-and-acceptance-2026-10-13.md)。
