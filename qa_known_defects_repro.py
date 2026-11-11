"""Reproduce defects of current WIP only. NOT a validation suite.
From package root: python qa_known_defects_repro.py.
Fix defects then replace negative probes with positive T01-T20 tests.
"""
from pathlib import Path
import sys
import numpy as np
import pandas as pd
sys.path.insert(0, str(Path(__file__).parent / "project"))
from mbv.baselines import compute_tod_baseline
from mbv.features import detect_bursts
from mbv.join import join_daily_vlr_mbv
from mbv.adapters import load_synthetic_minute_data
def check(title, cond, detail):
    print(("CONFIRMED" if cond else "NOT REPRODUCED")+": "+title+" — "+detail)
    if not cond:
        raise AssertionError("Expected known defect no longer reproduces: "+title)
bar=pd.DataFrame({"symbol":["A"],"ts":pd.to_datetime(["2026-01-05 09:30"]),"volume":[100.]})
future=pd.DataFrame({"symbol":["A"],"ts":pd.to_datetime(["2026-01-06 09:30"]),"volume":[10000.]})
other=future.copy();other["symbol"]="B";other["ts"]=bar.ts.iloc[0]
x=compute_tod_baseline(bar).iloc[0]
y=compute_tod_baseline(pd.concat([bar,future],ignore_index=True)).iloc[0]
check("T01/T02: future leakage",x==100 and y==5050,f"before={x} after={y}")
z=compute_tod_baseline(pd.concat([bar,other],ignore_index=True)).iloc[0]
check("T03: cross-symbol leakage",z==5050,f"shared baseline={z}")
raw=pd.DataFrame({"symbol":["A"],"ts":pd.to_datetime(["2026-01-05 09:30"]),"volume":[100.],"open":[10.],"high":[10.],"low":[10.],"close":[10.]})
baseline=pd.Series([10.],index=[raw.ts.iloc[0].time()])
check("body efficiency missing",bool(detect_bursts(raw.copy(),baseline).is_burst.iloc[0]),"flat candle incorrectly flagged")
zero=pd.Series([0.],index=[raw.ts.iloc[0].time()])
check("zero baseline",bool(np.isinf(detect_bursts(raw.copy(),zero).relative_volume.iloc[0])),"invalid infinity")
b0=pd.DataFrame({"symbol":["A"],"trade_date":["2026-01-05"]})
mbv=pd.DataFrame({"symbol":["A","A"],"trade_date":["2026-01-05"]*2,"burst_count":[1,2]})
check("duplicate-key inflation",len(join_daily_vlr_mbv(b0,mbv))==2,"one B0 record becomes two")
example=load_synthetic_minute_data("ignored.csv")
lunch=((example.ts.dt.time>=pd.Timestamp("11:30").time())&(example.ts.dt.time<pd.Timestamp("13:00").time())).sum()
check("lunch-gap violation",lunch==90,f"synthetic lunch bars={lunch}")
bad=((example.high<example[["open","close","low"]].max(axis=1))|(example.low>example[["open","close","high"]].min(axis=1))).any()
check("invalid OHLC",bool(bad),"synthetic OHLC bounds violated")
print("Known defects reproduced; this is NOT passing acceptance.")
