"""Compare TDX exported formula outputs against Python replica.

CSV must contain: open, high, low, close, volume, date,
and TDX_Z, TDX_RVRAW, TDX_DIR, TDX_RHO, TDX_EU, TDX_VU, TDX_ABU.
Do not claim parity without authentic TDX export data.
"""
from __future__ import annotations
import argparse
import numpy as np
import pandas as pd
from vlr import calculate

NUMERIC = {"Z":"TDX_Z","RVRAW":"TDX_RVRAW",
           "DIR":"TDX_DIR","RHO":"TDX_RHO"}
BOOLEAN = {"EU":"TDX_EU","VU":"TDX_VU","ABU":"TDX_ABU"}

def compare(df:pd.DataFrame, *, initial_tr:str="hl", tolerance:float=1e-6):
    result=calculate(df,initial_tr=initial_tr)
    report={}
    for key,col in NUMERIC.items():
        if col not in df:
            raise ValueError(f"Missing TDX export column: {col}")
        truth=pd.to_numeric(df[col],errors="coerce")
        good=truth.notna()
        if not good.any():
            raise ValueError(f"No comparable data in {col}")
        errors=(result.loc[good,key]-truth.loc[good]).abs()
        report[key]={"max_abs_error":float(errors.max()),
                     "compared_bars":int(good.sum()),
                     "pass":bool((errors<=tolerance).all())}
    for key,col in BOOLEAN.items():
        if col not in df:
            raise ValueError(f"Missing TDX export column: {col}")
        truth=pd.to_numeric(df[col],errors="coerce")
        good=truth.notna()
        mismatch=result.loc[good,key].astype(bool).ne(truth.loc[good].ne(0))
        report[key]={"mismatches":int(mismatch.sum()),
                     "compared_bars":int(good.sum()),
                     "pass":not bool(mismatch.any())}
    return report

def main():
    ap=argparse.ArgumentParser()
    ap.add_argument("csv")
    ap.add_argument("--initial-tr",choices=["hl","missing"],default="hl")
    ap.add_argument("--tol",type=float,default=1e-6)
    args=ap.parse_args()
    df=pd.read_csv(args.csv)
    report=compare(df,initial_tr=args.initial_tr,tolerance=args.tol)
    for key,value in report.items():
        print(key,value)
    if not all(r["pass"] for r in report.values()):
        raise SystemExit("TDX parity FAILED")
    print("TDX parity PASSED for compared exported series")

if __name__=="__main__":
    main()
