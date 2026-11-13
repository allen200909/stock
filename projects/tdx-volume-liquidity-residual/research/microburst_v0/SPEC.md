# MBV V0.1 技术规格说明 (`SPEC.md`)

## 1. 模块定位
MBV（Microburst Validation Layer）是独立于通达信 **VLR V2.1.2（Frozen Baseline B0）** 的日内成交结构解释与验证研究层。
- **不做实盘买卖信号、订单指令或资金曲线宣称**。
- **不将分钟 OHLCV 代理解释为真实主动买卖流或逐笔订单簿深度**。
- **不修改既有 `vlr.py` B0 算法与阈值**，仅通过只读适配器关联同证券同交易日特征。

## 2. 核心数学定义（Clean-room 独立规格）

### 2.1 时间槽位与滞后同槽位中位数基准（Past-only TOD Baseline）
对证券 $s$、交易日 $t$、日内分钟槽位 $k$（规范化为 `Asia/Shanghai` 的 K 线**开始时间**）：
- 正常 A 股连续竞价时段：`09:30 <= ts < 11:30` 与 `13:00 <= ts < 15:00`（5 分钟共 48 个槽位；1 分钟共 240 个槽位）。
- 收盘集合竞价窗口：`14:57 <= ts < 15:00`（1 分钟模式下标记 `closing_auction_window=True`，支持包含/排除两组稳健性配置）。
- 滞后基准仅使用 $t$ **之前已完成**的最近 $L=20$ 个有效交易日同槽位正成交量（`V > 0`），且有效历史天数不少于 $M=15$：
$$B_{s,t,k} = \operatorname{median}\{V_{s,u,k} : u < t,\ V_{s,u,k} > 0,\ |\mathcal{H}_{s,t,k}| \le 20\}$$
若 $|\mathcal{H}_{s,t,k}| < 15$，标记槽位状态为 `INSUFFICIENT_HISTORY`；若基准 $\le 0$ 或缺失，记 `BASELINE_INVALID`，对应相对量 $R_{s,t,k} = \text{NaN}$（绝不产生 $\infty$）。

### 2.2 相对量与实体效率代理
$$R_{s,t,k} = \frac{V_{s,t,k}}{B_{s,t,k}}, \qquad E_{s,t,k} = \frac{C_{s,t,k} - O_{s,t,k}}{\max(H_{s,t,k} - L_{s,t,k},\ \text{tick})}$$
微爆量事件指示器（默认 `rel_vol_threshold=2.5`, `body_eff_threshold=0.10`, `tick=0.01`）：
$$I_{s,t,k} = \mathbf{1}\{R_{s,t,k} \ge 2.5\} \cdot \mathbf{1}\{|E_{s,t,k}| \ge 0.10\}$$
注意：$E=0$（如 $O=C$ 平盘或一字板 $H=L=O=C$）时 $|E|=0 < 0.10$，不会误触发方向爆量。

### 2.3 当日聚合主特征
设当日有效且具备有效历史基准的槽位集合为 $\Omega_{s,t}$，总有效成交量 $V = \sum_{k \in \Omega} V_k$，爆量槽位集合 $S = \{k \in \Omega : I_k = 1\}$，$n = |S|$：
- **覆盖率门禁**：`valid_slot_coverage = available_valid_slots / expected_slots`。当覆盖率 `< 0.95`、`V <= 0` 或基准有效槽位不足时，主特征置 `NaN`（不误填 0），并输出明确的 `feature_status`（`LOW_COVERAGE` / `NO_VOLUME` / `INSUFFICIENT_HISTORY` / `SUSPENDED` / `DATA_INVALID`）。
- `burst_count`: $n = |S|$（仅在 `feature_status == 'OK'` 时为非负整数，否则为 `NaN`）。
- `burst_share`: $\sum_{k \in S} V_k / V$（`OK` 且 $n=0$ 时为 `0.0`）。
- `peak_ratio`: $\max_{k \in \Omega} R_k$。
- **自主定义事件权重**（非第三方脚本公式）：
  $$w_k = \frac{V_k}{V} \cdot \min\left(\frac{R_k}{2.5},\ 10.0\right) \cdot |E_k|, \quad k \in S$$
- `burst_dominance`: $\frac{\sum_{k \in S} \operatorname{sign}(E_k) w_k}{\sum_{k \in S} w_k} \in [-1, 1]$（当 $n=0$ 或 $\sum w_k \le 0$ 时为 `NaN`）。
- `burst_concentration`: 设 $\text{raw\_hhi} = \sum_{k \in S} (w_k / \sum w)^2$：
  - $n = 0$: `NaN`, `single_burst_flag = False`
  - $n = 1$: `1.0`, `single_burst_flag = True`
  - $n > 1$: $(\text{raw\_hhi} - 1/n) / (1 - 1/n)$, `single_burst_flag = False`
- `burst_direction_agreement`: 在与日线 B0 `DIR` 连接后计算：当 $|\text{B0\_DIR}| > \epsilon$ 且 $n \ge 1$ 时为 $\frac{\sum_{k \in S} \mathbf{1}\{\operatorname{sign}(E_k) = \operatorname{sign}(\text{B0\_DIR})\} w_k}{\sum_{k \in S} w_k}$，否则为 `NaN`。
- `vol_recon_error`: $|V_{\text{minute\_day}} - V_{\text{daily}}| / V_{\text{daily}}$，无同源日线量时标注 `RECONCILIATION_UNKNOWN`。
