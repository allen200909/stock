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
    if not np.isfinite(tolerance) or tolerance < 0:
        raise ValueError("tolerance must be finite and nonnegative")
    if "date" not in df:
        raise ValueError("Aligned TDX export requires date")
    result=calculate(df,initial_tr=initial_tr)
    # One common evaluation set; do not discard missing exports per column.
    evaluated = pd.Series(np.arange(len(df)) >= 145, index=df.index)
    count = int(evaluated.sum())
    if count == 0:
        raise ValueError("No post-warm-up bars to compare (need >145 bars)")
    report={}
    for key,col in (NUMERIC | BOOLEAN).items():
        if col not in df:
            raise ValueError(f"Missing TDX export column: {col}")
        truth=pd.to_numeric(df.loc[evaluated,col],errors="coerce")
        if not np.isfinite(truth.to_numpy(dtype=float)).all():
            raise ValueError(f"Missing or invalid post-warm-up export: {col}")
        actual=result.loc[evaluated,key]
        if not np.isfinite(actual.to_numpy(dtype=float)).all():
            raise ValueError(f"Nonfinite Python output: {key}")
        if key in BOOLEAN:
            if not truth.isin([0,1]).all():
                raise ValueError(f"Boolean export must be 0/1: {col}")
            mismatch=actual.astype(bool).ne(truth.astype(bool))
            report[key]={"mismatches":int(mismatch.sum()),
                         "compared_bars":count,"pass":not bool(mismatch.any())}
        else:
            errors=(actual-truth).abs()
            report[key]={"max_abs_error":float(errors.max()),
                         "compared_bars":count,"pass":bool((errors<=tolerance).all())}

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
