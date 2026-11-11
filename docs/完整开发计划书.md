# 量价流动性残差 × Microburst 验证模块 V0.1

**Claude Code 工程实施计划书（可执行规格 / Research RFC）**

- **发布日期**：2026-11-08
- **执行方**：Claude Code
- **项目仓库**：`allen200909/stock`
- **目标路径**：`projects/tdx-volume-liquidity-residual/research/microburst_v0/`
- **基线**：VLR B0（通达信 V2.1.2 Frozen Baseline）；E1–E4 仅作可选稳健性对照
- **项目代号**：MBV — Microburst Validation Layer
- **阶段**：V0.1 研究原型，不是实盘交易系统
- **变更策略**：新建 `feature/vlr-microburst-v0` 分支；不覆盖稳定指标、不改写旧选股器、不合并 `v2.2-experimental` 的变更

> 本文是授权 Claude Code 执行开发、单元测试、文档、研究报告和本地提交的任务规格。推送远端、创建 PR、合并及发布，遵循用户在 Claude Code 环境中的具体授权；禁止无授权修改主分支。需要真实数据或人工通达信/TradingView验证的步骤，必须标为待验证，不得伪造通过记录。

---

## 0. 已核实的工程基线与先决限制

### 0.1 现有仓库事实（2026-11-08 阅读）

- 主路径：`projects/tdx-volume-liquidity-residual/`。
- `README.md` 指定 **V2.1.2（Frozen Baseline）**；稳定基线不可因新增研究模型而被替换。
- 已有 `verify/vlr.py` 的 `vlr.calculate(df, model='B0')`，提供 B0、E1、E2、E3、E4，并输出六类事件、活跃度状态、选股结果；已有 `verify/tdx_parity.py`、`verify/inference.py`、`verify/trade_study.py`、`verify/confirmation.py` 等研究工具。
- 基线的逐 K **真实通达信对拍尚未完成**，工具通过合成测试不等于 TDX 正式验收。
- 仓库明确：2021–2026 的历史残差分布已经被研究者查看，不得重新标记为完全未接触的设计留出样本。
- 既有验证协议：收盘 T 确认、T+1 最早交易；1/3/5/10/20 交易日事件观察；按成交量、日期和市场状态设置对照；报告 calendar-block bootstrap 与成本假设。
- 既有 B0 的 ATR 是 TDX `SMA(TR, ATRN, 1)`，**不是普通算术 MA**；复用现有 Python 实现，禁止另写一个“近似 B0”。

### 0.2 外部脚本与许可边界

参考研究对象：Zeiierman 的 `LTF Volume Microburst Bubbles`，用户提供的 Pine Script v6 源码，头部注明 **CC BY-NC-SA 4.0**。

其研究思想：低周期相对放量门槛（默认 2.5）、方向性实体占振幅比例（默认 0.10）、爆量事件方向能量、事件集中度，以及在高周期聚合展示。

**本项目采用 clean-room 独立实现**：允许描述数学思想和研究假设，不复制原脚本的注释、绘图封装、函数结构、源码及独特表现形式。文档保留来源及许可说明。若日后决定从原脚本移植代码，先单独开展许可证审查，再落实署名、非商业与相同方式共享条款；不得擅自将 CC BY-NC-SA 代码混入许可不兼容的公共/商业仓库。

### 0.3 明确不做

- 不生成实盘买卖指令、订单、仓位控制、自动交易或资金曲线宣称。
- 不将一分钟成交量代理解释为真实主动买盘、逐笔资金流向或订单簿流动性。
- 不修改 `indicator/volume_liquidity_residual_v2.1.2.tdx` 与现有 3 个 selector；不改 B0 阈值；不让 MBV 倒灌原始 B0 信号。
- 不以“模型输出了漂亮的图”替代统计有效性验证。
- 不伪称拥有 QMT/PTADE 数据、不自动下载未经确认的数据、不填造收益与回测数字。
- 不将 `request.security_lower_tf()` 的历史输出视为天然“无重绘”。

---

## 1. 研究问题与预注册假设

**总问题：** 在控制日线 RVOL、VLR B0 的 Z/DIR、日期与市场状态后，分钟级异常成交结构是否仍能解释未来价格行为或区分既有量价信号？

**H1（核心）**：同属于日线 `EU`（强扩↑）的事件中，较高的多头微爆量方向优势与爆量占比，是否能带来不同的未来收益、MFE/MAE 或风险分布？

**H2（核心）**：同属于日线 `ABU`（吸收多）候选事件中，高爆量占比但日内方向优势偏弱/相互抵消的子组，其后续走势是否有可区分的统计分布？

**H3（探索）**：`VU`（真空↑）中是否存在“没有显著分钟爆量”与“少数分钟有局部爆量”两种不同机制？

`VD/ED/ABD` 只做风险/走势恶化的研究标签，不设计做空策略。所有 H1/H2/H3 均为待检验假设，不能提前写为研究结论。

**主要比较**：VLR-only vs. VLR+MBV；同时对比 RVOL-only、DIR-only、MBV-only 和条件/置换对照。主评价指标与阈值在查看验证期未来收益前冻结。

---

## 2. 技术架构与模块边界

```text
已存在的 VLR 项目（只读接口）
  verify/vlr.py -> calculate(OHLCVA, model='B0')
                       |
                       | T 日 VLR 因子和六类事件
                       v
独立新增 research/microburst_v0/
  data_adapters/   本地 CSV/Parquet + 可选 QMT/PTADE 接口
  validation/      分钟K和日K数据质量/时段/复权/成交量口径检查
  features/        分时相对量基线、爆量检测、聚合特征
  join/            与同证券同交易日日线 B0 事件合并
  studies/         条件分组、匹配对照、事件统计、负对照
  reports/         可复现报告输出和风险/缺口登记
  tests/           合成样本及属性测试
  config/          YAML 参数 + 版本/数据指纹
```

**原则**：纯函数优先；离线批处理；输入/输出有明确 schema；绝不在未知数据口径下静默继续；跨证券、跨交易日状态不得串联；不能让未来成交量进入历史时点的基准。

建议 Python 3.11+、pandas、numpy、pyarrow、pytest。复用现有 `verify/requirements.txt`，不强行升级项目全局依赖。CLI 可使用 argparse，避免为了 V0.1 引入重型框架。可增加 Ruff（若环境允许）。

---

## 3. 数据契约：优先级 P0

### 3.1 最小分钟K schema

`symbol, ts, open, high, low, close, volume[, amount]`

- `ts` 统一为 K 线**开始时间**，规范到 `Asia/Shanghai`；数据源若用收盘时间戳，适配器负责转换并记录源语义。
- `symbol` 包含交易所后缀（例如 `600000.SH`, `000001.SZ`），适配器须保留原始代码映射。
- `volume` 统一为**股**，不能把通达信或不同券商常见的“手”直接当股；`amount` 如有则统一为人民币元。
- 同 `(symbol, ts)` 不得重复；价格非负/合理、成交量非负；严格按时间排序。
- 必须记录 `source`, `source_version`, `frequency`, `timezone`, `timestamp_semantics`, `volume_unit`, `amount_unit`, `adjustment`, `ingestion_time`, `source_hash`。
- 禁止用未来日线字段填充本日分钟缺口；无数据应保留质量标记，不用 0 代替“未获取”。

### 3.2 日线 schema

`symbol, trade_date, open, high, low, close, volume[, amount]`，可选历史状态 `suspended, st_flag, board, listing_age_sessions, price_limit_status`；状态字段需点时有效、来源可验证，不允许默认 `False` 伪造。

- VLR 因子必须直接调用既有 Python `B0` 实现；正确处理其预热和日期顺序要求。
- 日线复权、分钟线复权、成交量及成交额变换必须一致。初版推荐先在未复权分钟价上提取**纯结构特征**，再用已经明确企业行为口径的 VLR 日线列做 join；事件与收益研究需要一致的收益计算口径。
- 缺少真实交易所日历时禁止执行正式 T+1 研究（单元测试可用人工构造的显式日历）。

### 3.3 A股交易时段（正常交易日）

- 上午：`09:30 <= ts < 11:30`；下午：`13:00 <= ts < 15:00`；夏令时概念不适用，使用 `Asia/Shanghai`。
- 正常 1分钟 240 个槽位，5分钟 48 个槽位；每个数据商需要验证其 time-label 规则、午间断档和交易日特殊情况。
- 开盘集合竞价成交若由数据商并入 09:30 K 线，必须有来源说明；**14:57–15:00 收盘集合竞价**若并入分钟线，则另设 `closing_auction_window` 标志，默认从主研究特征中分开统计，并开展包含/排除两组稳健性测试。
- 停牌、临停、缺分钟、上市初期、退市、ST、一字板、涨跌停、除权日、交易所特别日等要标注；不要认为 240/48 个K线缺失即自动等价停牌。

### 3.4 日内有效性与对账门禁

- **默认**：`coverage = available_valid_slots/expected_slots >= 0.95` 方可计算主要日特征；同时保留实际 `coverage` 数值。
- 没有足够往期同槽位基准样本、无交易量或分钟数据异常时，`feature_status=INSUFFICIENT_HISTORY/NO_VOLUME/DATA_INVALID/...`；**禁止将缺数日与“确实没有爆量”混为一类**。
- 分钟成交量合计 vs 同源日线成交量：输出相对偏差 `vol_recon_error`；若集合竞价归属或数据商口径不同，先解释差异并标注 `RECONCILIATION_UNKNOWN`；不能强行断言 2% 偏差即数据错误或直接放行。
- 数据商分钟历史覆盖长度、单次请求上限、时段连续性先运行探测诊断；有欠缺时保留 adapter scaffold 与合成测试，不编造数据。

---

## 4. MBV V0.1 因子定义（先冻结后测试）

### 4.1 当日同槽位历史量基准——主要方法

为防止午间、开盘及尾盘成交量季节性干扰，以同证券、同分钟槽位、**之前**已完成的交易日建立基准，而不是仅用当天逐分钟 EMA：

\[
B_{t,k}=\operatorname{median}\{V_{u,k}:u\text{ 为 }t\text{ 之前最近 }20\text{ 个可用交易日}\}
\]

\[
R_{t,k}=V_{t,k}/B_{t,k},\quad
E_{t,k}=(C_{t,k}-O_{t,k})/\max(H_{t,k}-L_{t,k}, tick)
\]

- 默认 `lookback_days=20, min_history_days=15`，且同槽位历史须有正值/有效成交量；零基准不给任意大比值，改记 `BASELINE_INVALID`。
- 只有已完成的先前交易日入库；计算某日特征时绝不能用当日其他分钟或未来日期训练该日基准。
- 以 5分钟作 V0.1 首选研究频率（数据覆盖更稳健），1分钟作为敏感性研究；不能在未对齐时间尺度时直接比较阈值的“含义”。
- 源脚本中的 session EMA 可设计成**可选 benchmark** `baseline_method=session_ema`，非 V0.1 主方法。其含当前分钟成交量的特征要标注为当期观察而非纯滞后预期。

### 4.2 异常成交事件（burst）

对每个有效分钟/5分钟槽位定义：

\[
I_{t,k}=\mathbf{1}\{R_{t,k}\ge 2.5\}\,\mathbf{1}\{|E_{t,k}|\ge 0.10\}
\]

`E>0` = 方向代理多头；`E<0` = 方向代理空头。`E=0` 不强行分类。阈值采用探索性原型默认值，不宣称有最优性；后续 sensitivity grid 需预先列出，避免后验调参。

**术语约束**：这里的 `E` 是K线实体效率代理，不是订单流不平衡；`I=1` 代表“异常量 + 明显方向实体”，不是实际买卖方主导的微观结构证据。

### 4.3 当日聚合主特征

仅以**有效交易时段、具备可用历史基准**的槽位为聚合空间。设 `S={k:I=1}`，`V=Σ有效V_k`。

1. `burst_count = |S|`。
2. `burst_share = Σ_{k∈S}V_k / V`（无事件且数据合格时为 0；数据不足为 NaN）。
3. `peak_ratio = max(R_k)`（在所有基准有效槽位中计算，解释时与 burst_count 分离）。
4. 自主定义事件权重 `w_k = (V_k / V) × min(R_k / 2.5, 10) × |E_k|`，只对 `k∈S`；上限10仅抑制离群值，并非 Zeiierman 原始分数。若所有事件权重和不大于0，则方向类因子为 NaN。
5. `burst_dominance = Σ_{k∈S}sign(E_k)w_k / Σ_{k∈S}w_k`，范围 [-1,1]。
6. `raw_hhi = Σ (w_k/Σw)^2`，`burst_concentration = (raw_hhi-1/n)/(1-1/n)`（`n>1` 时）；`n=1` 时定义为1，同时 `single_burst_flag=true`；`n=0` 为 NaN。
7. `burst_direction_agreement = Σ_{k∈S}I[sign(E_k)=sign(DIR_day)]×w_k/Σw_k`；`DIR_day` 接近0时定义 NaN（不强行分类）；采用滞后基线和当日收盘 DIR 时，因子只在收盘后输出。
8. `valid_slot_coverage`、`baseline_slot_coverage`、`vol_recon_error`、`burst_regime`（仅数据性标签，不是交易信号）、`feature_status`。

其中 `burst_concentration` 在 `n=1` 的值虽数学上高，但**不意味着统计可靠性高**，报告必须同时展示 `burst_count` 和覆盖率。避免仅凭单个事件给予极端高置信度。

### 4.4 后续扩展（V0.2 Backlog，不阻塞 V0.1）

- AM/PM、开盘30分钟/尾盘30分钟的爆量份额；成交量突发的持续性/间隔分布。
- 事件价位、后续回补和微观成本区验证；如需精确的 burst OHLC 必须保存原始事件时间戳与价位，**不能拿高周期K线 high/low 冒充事件K线高低点**。
- 不使用无法验证的机构持仓、主动买卖方向或订单簿推测。

---

## 5. 与既有 VLR B0 对接

必须以**左连接**保留每一个日线 B0 样本，不允许因分钟数据缺失悄悄删掉事件。连接键 `(symbol, trade_date)`，每日仅一行特征；多证券时不跨标的填充。

**联合输出**：

```text
symbol, trade_date,
B0_Z, B0_RVRAW, B0_DIR, B0_RHO,
B0_VU, B0_VD, B0_EU, B0_ED, B0_ABU, B0_ABD,
burst_count, burst_share, peak_ratio,
burst_dominance, burst_concentration, burst_direction_agreement,
valid_slot_coverage, baseline_slot_coverage, vol_recon_error,
feature_status, source_hash, params_hash
```

从 `verify/vlr.py` 获取原输出时保留原字段映射表；禁止修改 `verify/vlr.py` 以适应新因子。可建立只读 adapter 封装版本兼容，记录对应 Git commit SHA。

**因子与交易层分离**：一字板可以保留研究因子；`ST/停牌/涨跌停可成交性/IPO时段` 等在事件/执行表单独记录；缺少点时可成交字段时禁止声称可以成交。

---

## 6. 研究方案与统计学防护

### 6.1 研究数据分组

1. **A：VLR-only**：固定 B0 信号，不加入分钟因子。
2. **B：MBV-only**：仅分钟因子组合（在训练期冻结阈值或用连续解释变量）。
3. **C：VLR+MBV**：B0 事件内根据 MBV 预注册的方向/集中度分层。
4. **D：对照**：同交易日、相似 RVOL 桶及尽量同板块/行业/市值组匹配；匹配不到则记录失配比例，而不是放宽条件不披露。
5. **E：负对照**：同日或同 RVOL 分桶置换分钟因子；检查额外信息是否只是放量的替代品。

### 6.2 主要终点

- 未来 1/3/5/10/20 **交易日**的收益分布（明确使用一致复权收益价格）；多空方向仅作条件切分，A股场景不设计开空。
- MFE、MAE、胜率、均值/中位数、样本数及置信区间。
- **主要增量指标**在实验开始前指定：建议 H1 采用 `EU` 内对照调整后的未来5交易日收益差；H2 采用 `ABU` 内未来5交易日 MAE 差。其余仅作探索性诊断。
- 所有研究不得以日线收盘信号当日在收盘价成交；交易仿真最早 T+1，保留 `UNFILLED/ELIGIBLE_FOR_FILL_CHECK/PENDING/DATA_MISSING` 等状态。
- 有效事件数过低或置信区间宽时报告 `INCONCLUSIVE`，不得选择性删除失败分组。

### 6.3 验证与暴露历史

- 继承 `docs/validation-protocol.md`：2015–2020 训练/研究；2021–2026 数据暴露必须显著标注；真正独立确认样本需要**新的未来注册日期范围**及未看过的对应结果。
- 训练段定义 `burst_share/dominance/concentration` 的分组切点，后续固定；不在封存期查看收益后重设分组。
- 股票池必须尽可能点时构造并包括退市标的；仅用当前存续股票应显示 `SURVIVORSHIP_BIASED`。
- 前视检查：全数据计算 vs 截断到 T 日计算，对历史分钟聚合结果和 VLR join 后结果应一致（历史数据修订除外）。
- 横截面相关和持有期重叠使用日期块 bootstrap（复用 `verify/inference.py`），输出 block=5/10/20 的敏感性、置信区间与失败抽样数量；不存在真实数据时只跑合成单测。
- 除权/复权、涨跌停、交易日历、分钟成交量累计与日线口径必须随研究报告一起记录。

### 6.4 因果与解释限制

- `burst_share` 和 `burst_dominance` 很可能与 RVOL、DIR、TR/ATR 高度相关；必须检验增量，不得把相关性重新命名为 alpha。
- 分钟OHLCV只能建立交易行为代理，不等价真实交易主动方向/成交盘口深度/冲击成本因果估计。
- 当日分钟特征只有在当日收盘后完整可见，严禁用当日全量特征做盘中决策回测。

---

## 7. Claude Code 分阶段任务与工作包

### WP0｜仓库勘测、规格冻结、准备分支（P0）

执行：

1. 检查 `git status`、当前分支、最近提交、`README.md`、`docs/validation-protocol.md`、`verify/README.md`、`verify/vlr.py` 的实际 API；先保护未提交的用户改动。
2. 在新分支创建目标目录及 `SPEC.md`、`config/default.yaml`、`DATA_CONTRACT.md`、`THREAT_MODEL.md`。
3. 记录仓库基线 SHA、Python 版本、依赖版本、许可来源与所有待确认的数据差异。

验收：不得修改冻结基线；给出架构说明，所有配置项有默认值和输入验证。

### WP1｜数据验证与分钟特征引擎（P0）

执行：

1. 实现 CSV/Parquet 适配器；实现 QMT/PTADE 接口占位/有证据的可运行适配器，不在无 SDK 时捏造方法名。
2. 实现 `validate_minute_bars()`、`normalize_bar_timestamps()`、`build_tod_baseline()`、`detect_bursts()`、`aggregate_daily_features()`。
3. 实现缺数、对账、公司行为标记和严格 `feature_status`。
4. 用纯合成分钟样本做单元测试、前缀截断、跨证券隔离、交易时段回归测试。

验收：无未来泄漏、可复现、边界明确定义；单位不正确与重复时间戳 fail-closed；代码风格/类型检查合格。

### WP2｜VLR适配与事件研究（P1）

执行：

1. 以只读方式调用 `verify/vlr.py` 的 B0；加入 Schema 映射和基础对拍测试。
2. 实现 `join_daily_vlr_mbv()`；保持 VLR 全量日期，不匹配分钟记录应为 NaN + 状态，而非默认为0。
3. 实现分组、对照匹配、事件窗口、摘要和与现有 bootstrap 工具的适配。
4. 复用现有 `trade_study.py` 时需遵循其输入契约，不能误将事件研究收益当实盘成交收益。

验收：合成数据可完整产出报告；统计脚本展示样本流失、对照覆盖、每种状态计数；没有真实数据时报告只标 `SYNTHETIC_DEMO`。

### WP3｜可视化与 Pine v6 可行性评估（P2）

执行：

1. Python 侧先实现日线图的 B0_Z 与 MBV 特征对照、事件分布、覆盖率与质量状态报告图。
2. 撰写 `PINE_PORTABILITY.md`：TradingView `request.security_lower_tf()` 的 arrays、请求限制、数据时间粒度、实时修订、session 时段及历史深度的局限。
3. **可选**：若有测试和有效TradingView数据，将核心 `burst_count/burst_share/dominance` 移植为**单独** Pine v6 指标，主频率默认 5 分钟；对齐 Python 的分钟/5分钟定义并人工编译与逐K对照。

验收：Pine 编译/跨平台数值对照**只能在实际完成后打勾**；无TradingView实测时交文档与 `NOT_VERIFIED` 状态，不阻塞 Python V0.1 研究引擎交付。

### WP4｜复核、报告、打包交付（P0）

执行：

1. 在可用环境跑全套旧项目测试 + 新模块测试；保留终端日志、版本、命令、样本/hash。
2. 运行 `git diff --check` 与变更范围清点，确认未改稳定基线及其它项目。
3. 写 `QA_REPORT.md`（每项测试实际证据）、`LIMITATIONS.md`、`RESEARCH_PROTOCOL.md`、`REVIEW_REQUEST.md`。
4. 本地提交到独立分支（若环境允许），输出变更文件清单、测试命令、commit SHA；未经用户明确授权不合并 master，不擅自宣称远端已更新。

验收：能够由另一位开发者在干净环境执行 README 中完整命令，重现**合成样本**结果；真实数据缺失项全部明确标红/标待验证。

---

## 8. 建议项目目录（允许细微调整，须解释）

```text
projects/tdx-volume-liquidity-residual/
  research/
    microburst_v0/
      README.md
      SPEC.md
      DATA_CONTRACT.md
      RESEARCH_PROTOCOL.md
      PINE_PORTABILITY.md
      LICENSE_PROVENANCE.md
      THREAT_MODEL.md
      LIMITATIONS.md
      REVIEW_REQUEST.md
      QA_REPORT.md
      pyproject.toml                  # 可选；避免破坏旧依赖
      config/default.yaml
      mbv/
        __init__.py
        schema.py
        sessions.py
        adapters.py
        baselines.py
        features.py
        aggregate.py
        join.py
        event_study.py
        cli.py
      tests/
        test_schema.py
        test_sessions.py
        test_baselines.py
        test_features.py
        test_prefix_invariance.py
        test_join.py
        test_event_study.py
        test_fails_closed.py
      fixtures/
        synthetic_minute.csv          # 明确标为人工合成数据
        synthetic_daily.csv
      outputs/                        # gitignore 真实数据/大型结果
```

**预期CLI（名称可按实际目录调整，但必须有等价可重复入口）**：

```bash
python -m mbv.cli inspect-data --minute <file> --daily <file> --config config/default.yaml
python -m mbv.cli compute-features --minute <file> --config config/default.yaml --out <parquet>
python -m mbv.cli join-vlr --daily <file> --features <parquet> --out <parquet>
python -m mbv.cli study --joined <parquet> --calendar <file> --config config/default.yaml --outdir <dir>
python -m pytest tests -q
```

如果某命令需要额外价格、收益或历史状态文件，CLI 必须在 `--help` 中准确列出并验证；以上是接口目标，不是宣称已运行的命令。

---

## 9. 验收矩阵：必须自动化测试

| ID | 测试场景 | 预期 |
|---|---|---|
| T01 | 当前分钟异常量增加 | 同槽位基准不因当前或未来数据改变 |
| T02 | 将输入截断到 T 日 | 先前日特征数值不变（前缀不变性） |
| T03 | 两证券同一时间混合输入 | 基准/状态互不串联 |
| T04 | 11:30–13:00 午间休市 | 不产生错误缺失K线与人工爆量 |
| T05 | 不同商的 K线开盘/结束时间戳 | 规范化后一致；歧义明确报错 |
| T06 | 1分钟/5分钟正常交易日 | 期待 240/48 槽位；特殊时段标记 |
| T07 | 样本中有零量、H=L、负量、重复TS | 合理边界、拒绝坏数据、无无穷和伪爆量 |
| T08 | 有效分钟覆盖率不足95% | `feature_status` 非 OK，数值不误填0 |
| T09 | 不足15个历史同槽位日 | `INSUFFICIENT_HISTORY`，不输出伪高相对量 |
| T10 | 所有事件为0/仅1次事件/正反方向对冲 | 比例、方向和集中度符合预设数学规则 |
| T11 | 5分钟暴量与普通放量样本 | 能区分集中爆发和均匀放量（人工构造） |
| T12 | 分钟数据缺失但B0日线有事件 | join后保留日线事件，MBV 为 NA+状态 |
| T13 | 企业行为、涨跌停、一字板、停牌恢复 | 事件保留，数据风险/可成交状态单独标记 |
| T14 | 日线B0重复日期/分钟重复ts | fail-closed，不双重计数 |
| T15 | 日线 B0 接口与原模型 | 输出不变，绝不改写B0实现 |
| T16 | 未提供真实交易日历 | 正式事件收益/执行研究拒绝运行 |
| T17 | 事件研究含未来收益 | 只作标签；T 日特征文件不含未来收益列 |
| T18 | 匹配对照无候选/样本过少 | 明确 `INCONCLUSIVE`，不伪造组别 |
| T19 | 跨日期 bootstrap | 复用现有工具并与人工小样本核验 |
| T20 | 使用合成数据运行研究报告 | 结果醒目标 `SYNTHETIC_DEMO`，不作 alpha 宣称 |

**质量门槛**：T01–T20 自动测试全部通过（实现过程可增加测试，不能无理由删减）；无异常的 `NaN/inf`；固定随机种子；提交测试日志和 commit SHA。`git diff` 不得出现对稳定基线文件的意外修改。所有真实数据或实盘验收独立于自动化单测记录。

---

## 10. Gate / 停止与升级规则

### G0：代码安全门禁（必过）

- 项目不覆盖冻结文件；数据 schema、零量与时间规范化验证通过；前视测试通过；合成演示完整；README 能重现。
- 若不满足：不得进入研究结论输出，先修软件。

### G1：真实数据门禁（未满足时允许只交研究框架）

- 明确 QMT/PTADE 版本与导出样本；同源日线分钟线对账；1/5分钟数据可用性与缺数率；真实交易日历；处理公司行为。
- 若用户本机数据不可访问：报告 `BLOCKED_REAL_DATA` 并交付全部可运行本地解析与测试，不冒充验证。

### G2：真实 B0 对拍门禁（已有项目仍待解决）

- 需要用户真实通达信诊断导出、实机编译及完整21输出逐K对拍。若尚未通过，联合事件研究只标 **PROVISIONAL_RESEARCH**。

### G3：统计门禁（真实数据才可评判）

- 条件对照、事件样本数、成本/可成交性假设、区块 bootstrap、训练/验证/前瞻样本隔离完整；效果稳定且增量明确，才建议进一步合并研究。
- 若结果弱或方向不稳：标记 `NO_EVIDENCE_OF_INCREMENTAL_VALUE` 或 `INCONCLUSIVE`，保留独立模块，不优化阈值来追逐已见过的样本。

### 最终合并政策

只有独立审阅、G0–G3 及必要的人工平台验收通过后，才能提出合入旧指标的下一版 RFC。V0.1 **不合并、不改信号**。

---

## 11. Claude Code 最终交付格式

最终答复必须按以下标题逐项输出（附实际证据，不得只有“测试通过”）：

1. **变更摘要**：仓库原始 SHA、新分支名、新提交 SHA、改动文件清单。
2. **算法实现**：核心公式、参数来源、为何选择同槽位基准而不是当前值 EMA、事件是否仅基于分钟OHLCV代理。
3. **运行命令**：新模块、旧基线回归测试、输入样例、输出样例。
4. **QA 表格**：每个 T01–T20 `PASS/FAIL/NOT_RUN` + 相关日志与原因。
5. **数据质量**：来源、交易时段、量单位、复权、公司行为、分钟日线对账、缺失覆盖情况。
6. **结果**：严格区分 `SYNTHETIC_DEMO`、`EXPLORATORY_REAL_DATA`、`CONFIRMATORY_OOS`；未获真实数据就不能生成实证收益报告。
7. **仍未满足的 Gate**：真实数据、TDX对拍、TradingView编译、回测及样本外的具体缺口与所需材料。
8. **待复核请求**：把关键设计选择、风险点、建议第二位 Agent 重点审核的文件路径列出。

---

## 12. 给 Claude Code 的明确执行指令

请按 WP0 → WP1 → WP2 → WP4 顺序完成 **V0.1 Python 独立研究模块**；WP3 Pine 编译验证属于选做，不能用未验证的 Pine 版本替代通过测试的 Python 版本。不要为了等待数据或批准而停下可独立完成的软件任务。若实际仓库 API 与本文不同，以仓库真实实现为准，但须记录差异并保持冻结基线不变。全部代码、测试、文档和可复现合成演示完成后，输出上述验收报告，供独立审查。不要擅自合并到稳定版。

### 参考链接与资料

- 现有项目：`https://github.com/allen200909/stock/tree/master/projects/tdx-volume-liquidity-residual`
- 项目真实基线：`.../README.md`、`.../docs/model-notes.md`、`.../docs/validation-protocol.md`、`.../verify/README.md`
- TradingView 官方 LTF request：`https://www.tradingview.com/pine-script-docs/concepts/other-timeframes-and-data/`
- TradingView 官方运行限制：`https://www.tradingview.com/pine-script-docs/writing/limitations/`
- TradingView 官方重绘说明：`https://www.tradingview.com/pine-script-docs/concepts/repainting/`
- 原始 Microburst 研究资料：用户提供的 Zeiierman Pine v6 代码（CC BY-NC-SA 4.0）；**原计划书 V0.1 初版未附原始源码，本次按用户要求将用户提供的参考脚本单独置于 `third_party/` 并附许可说明；不得将其直接并入 Apache-2.0 模块**。

**负责人裁定：在未经验证增量之前，将 MBV 定位为“分时成交结构解释与验证层”，而非交易信号生成器。**