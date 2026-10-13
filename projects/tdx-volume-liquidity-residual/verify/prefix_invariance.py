"""Prefix invariance regression over all five research models."""
from __future__ import annotations
import argparse
import numpy as np
import pandas as pd
from vlr import calculate

COLUMNS = ["Z","RVRAW","DIR","RHO","EU","VU","ABU","VD","ED","ABD",
           "XG3","XG6010","XGLAYER","HOT","FADING","OTHER"]

def run(df: pd.DataFrame, checkpoints: int = 20) -> None:
    if len(df) < 340:
        raise ValueError("need >=340 historical bars")
    ends=np.unique(np.linspace(300,len(df)-1,num=checkpoints,dtype=int))
    for model in ("B0","E1","E2","E3","E4"):
        full=calculate(df,model=model)
        for end in ends:
            short=calculate(df.iloc[:end+1],model=model)
            for name in COLUMNS:
                a,b=full.iloc[end][name],short.iloc[-1][name]
                if isinstance(a,(bool,np.bool_)):
                    assert a==b,(model,end,name,a,b)
                else:
                    assert np.isclose(a,b,atol=1e-9,rtol=0,equal_nan=True),(
                        model,end,name,a,b)
        layers=["HOT","QUIET","WARMUP","ACTIVE","HIGHACT",
                "LONGACT","FADING","OTHER"]
        assert (full[layers].sum(axis=1)==1).all(),model
        assert full["XGLAYER"].equals(full["ACTIVE"]|full["HIGHACT"])
        print(f"PASS {model}: {len(ends)} prefix checkpoints, 8-way partition")

def main():
    parser=argparse.ArgumentParser()
    parser.add_argument("csv",help="OHLCV CSV, including amount for E4")
    parser.add_argument("--points",type=int,default=20)
    args=parser.parse_args()
    run(pd.read_csv(args.csv),args.points)

if __name__=="__main__":
    main()
