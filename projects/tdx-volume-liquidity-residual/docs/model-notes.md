# 模型说明与研究假设

> V2.1.2 是冻结基线。本文档描述其实际实现，不把尚未完成验证的假设写成结论。

## 1. 统计结构

核心关系：

```text
MOV = TR / prior ATR
RVOL = VOL / prior volume mean
RVFIT = min(RVOL, RVCAP)
MOVFIT = min(MOV, MVCAP)
MOV_hat = REGB + REGK * RVFIT
Residual = MOV - MOV_hat
Z = (Residual - prior residual mean) / prior residual std
```

当前 K 线只作为被检测样本，不参与自己的 ATR/成交量基准、滚动回归或残差均值/标准差。

注意：预测端使用的是 `RVFIT`，并非完全原始 `RVRAW`。因此 RVRAW>RVCAP 的巨量样本存在截尾外推风险。

## 2. “截尾”术语

当前：

```text
RVFIT=min(RVRAW,3)
MVFIT=min(MOV,4)
```

属于**固定上限截尾**，不是按样本分位数定义的统计 Winsorization。后续文档统一使用“上限截尾”。

## 3. 正斜率约束与模型质量

```text
REGK = max(raw slope, 0)
```

当 RHO<0 时，说明历史量价关系方向与模型工作假设相反：

- R2RAW=RHO²：原始线性关系强度；
- R2POS=max(RHO,0)²：符合正向工作假设的有效关系强度。

R2RAW 不能单独作为“模型质量越高越好”的过滤。

## 4. DIR

```text
DR  = (C - REF(C,1)) / TR
DB  = (C - O) / TR
CLV = (2*C - H - L) / (H-L)
DIR = (WDR*DR + WDB*DB + WCV*CLV) / (WDR+WDB+WCV)
```

默认：

```text
WDR=0.50
WDB=0.25
WCV=0.25
```

权重归一化用于保持 DIR 尺度稳定。

## 5. 已知统计问题：异方差

V2.1.2 用统一历史残差标准差构造 Z。外部审查的样本复刻发现，残差离散度会随 RVOL 明显增大。这意味着同一个 ±1.5 阈值在不同量能 regime 下未必代表相同稀有程度。

因此当前“成交量条件下异常”的解释需要进一步验证。V2.2 实验分支测试：

1. Linear + JUMBO regime；
2. Log-linear；
3. Log-linear + conditional scale；
4. AMOUNT variant。

新模型是否更好，以 OOS 事件研究而不是“Z 更像正态分布”决定。

## 6. 活跃度分层

强扩事件先以 COOL=3 去重，再统计 CNT60/CNT20/CNT10。

完整状态：

- QUIET
- WARMUP
- ACTIVE
- HIGHACT
- LONGACT
- HOT
- FADING
- OTHER

其中 FADING 用于表示“过去有活跃强扩，但近 10 日没有新强扩”；它可能具有趋势衰减信息，暂不进入默认选股。

## 7. 使用边界

- 指标只在收盘后确认；
- T 日信号的策略执行统一从 T+1 开始；
- 原始因子层与 A 股可成交性过滤分离；
- 一字板等事件可以是有效的流动性现象，但不等于可以买入；
- 未完成 OOS 与成本检验前，不宣称存在可交易 alpha。

验证细则见 `validation-protocol.md`。
