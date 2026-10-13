# 模型说明与测试记录

## 1. 统计结构

核心关系：

```text
MOV = TR / prior ATR
RVOL = VOL / prior volume mean
MOV_hat = REGB + REGK * winsorized(RVOL)
Residual = MOV - MOV_hat
Z = (Residual - prior residual mean) / prior residual std
```

当前K线只作为被检测样本，不参与自己的基准、回归或残差标准化。

## 2. 为什么使用正斜率约束

模型的工作假设是“成交量增加通常伴随更大的正常波动”。因此回归斜率：

```text
REGK = max(raw slope, 0)
```

当 RHO < 0 时，表示样本存在与模型假设相反的关系。此时：

- R2RAW = RHO²：保留原始线性关系强度；
- R2POS = max(RHO,0)²：表示符合正相关假设的有效关系强度。

不要用 R2RAW 单独做“模型质量越高越好”的过滤，否则强负相关样本也会被误判为高质量。

## 3. DIR

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

权重做归一化，避免调参时改变 DIR 的整体尺度。

## 4. 量能梯度

```text
RVOL < 1.20       真空候选区
1.20 <= RVOL      强扩候选区
RVOL > 1.50       吸收最低放量要求
```

强扩与吸收不会因量能区间产生逻辑冲突，因为它们分别位于 Z 的正负两侧。

## 5. 活跃度分层

强扩事件先以 COOL=3 去重，再统计：

- CNT60：中期强扩频率
- CNT20：近期密度
- CNT10：短期密度

“次数多”不自动等于“更优”：

- 60日高频但近期不密集，可视为持续高活跃；
- 10日>=3 或20日>=4，标记为 HOT，表示近期扩张过于集中。

## 6. 建议验证

至少记录：

- forward return: 1/3/5/10/20日
- win rate
- MFE
- MAE
- signal count
- median / mean return
- ACTIVE / HIGHACT / LONGACT / HOT 分组表现
- RHO / R2RAW / R2POS 分层表现

在完成事件研究前，不建议加入 EMA/MA 趋势条件到核心残差公式内。
