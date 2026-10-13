from __future__ import annotations
import argparse
import pandas as pd
from vlr import calc

def main():
    ap=argparse.ArgumentParser()
    ap.add_argument("csv")
    ap.add_argument("--points",type=int,default=20)
    a=ap.parse_args()
    df=pd.read_csv(a.csv)
    if len(df)<250:
        raise SystemExit("need >=250 rows")
    full=calc(df)
    ends=[int(200+i*(len(df)-201)/max(a.points-1,1)) for i in range(a.points)]
    cols=["Z","RVRAW","DIR","RHO","EU","VU","ABU"]
    bad=[]
    for end in ends:
        pref=calc(df.iloc[:end+1])
        for col in cols:
            x=full.iloc[end][col]; y=pref.iloc[-1][col]
            if col in {"EU","VU","ABU"}:
                ok=bool(x)==bool(y)
            else:
                ok=(pd.isna(x) and pd.isna(y)) or abs(float(x)-float(y))<=1e-10
            if not ok:
                bad.append((end,col,x,y))
    if bad:
        for item in bad[:20]:
            print("FAIL",item)
        raise SystemExit(f"{len(bad)} mismatches")
    print(f"PASS: {len(ends)} prefixes x {len(cols)} series")

if __name__=="__main__":
    main()
