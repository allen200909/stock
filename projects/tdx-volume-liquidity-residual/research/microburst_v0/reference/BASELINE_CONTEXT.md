# VLR B0 离线参考代码边界

这里提供现有冻结 VLR B0 (V2.1.2) Python 研究实现的只读快照。

- `vlr_verify/vlr.py`: calculate(df, model='B0')；需要每只证券按时间排序的有效 OHLCV。
- `vlr_verify/validation.py`: daily_dates / finite_numeric 校验器。
- `vlr_verify/inference.py`: 需要真实事件收益及交易所日历时使用的 block_bootstrap。
- `vlr_verify/requirements.txt`: 依赖。

离线导入示例：
```python
import sys
sys.path.insert(0,'/FULL/PATH/TO/reference/vlr_verify')
from vlr import calculate
result = calculate(daily_df, model='B0')
```

严格保持原文件只读；不得修改 VLR V2.1.2 的指标/选股公式、信号定义及基线验收标准。B0 的 Python 研究复刻尚未通过真实通达信全部21项输出逐K对拍，不代表已证实交易alpha。日线信号T收盘后确认、最早T+1执行；需真实涨跌停、停牌、公司行为及交易日历数据。

缺少真实 QMT/PTADE 分钟数据时，输出仅限 SYNTHETIC_DEMO。既有2021–2026部分研究样本不能重新宣称为未观察OOS。
