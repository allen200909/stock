"""Deterministic structural tests; synthetic data are not trading evidence."""
from __future__ import annotations
import unittest
import numpy as np
import pandas as pd
from vlr import calculate
from execution import build_execution_table

def sample(n=440):
    rng=np.random.default_rng(20261013)
    logret=rng.normal(.0003,.021,n)
    close=20*np.exp(np.cumsum(logret))
    op=np.r_[close[0],close[:-1]]*np.exp(rng.normal(0,.004,n))
    hi=np.maximum(op,close)*(1+rng.uniform(0,.012,n))
    lo=np.minimum(op,close)*(1-rng.uniform(0,.012,n))
    vol=rng.lognormal(13,.55,n)
    return pd.DataFrame({"open":op,"high":hi,"low":lo,"close":close,
                         "volume":vol,"amount":vol*close})

class VLRTests(unittest.TestCase):
    def test_no_future_and_partition(self):
        df=sample()
        keys=["Z","EU","VU","ABU","VD","ED","ABD",
              "XG3","XG6010","XGLAYER"]
        layers=["HOT","QUIET","WARMUP","ACTIVE","HIGHACT",
                "LONGACT","FADING","OTHER"]
        for model in ("B0","E1","E2","E3","E4"):
            full=calculate(df,model=model)
            self.assertTrue(full[layers].sum(axis=1).eq(1).all())
            for end in [301,340,400,439]:
                short=calculate(df.iloc[:end+1],model=model)
                for key in keys:
                    a,b=full.iloc[end][key],short.iloc[-1][key]
                    if isinstance(a,(bool,np.bool_)):
                        self.assertEqual(a,b,(model,end,key))
                    else:
                        self.assertTrue(np.isclose(a,b,atol=1e-9,rtol=0,
                                                   equal_nan=True),
                                        (model,end,key))
    def test_executability_no_fill_assumption(self):
        dates=pd.bdate_range("2026-01-01",periods=35)
        bars=pd.DataFrame({"date":dates,"ticker":"T",
                "RAW_SIGNAL":[False]*20+[True]+[False]*14,
                "amount":100_000_000,"is_st":False,
                "listing_age_days":300,"suspended":False,
                "limit_up_locked":False,"limit_down_locked":False})
        bars.loc[21,"limit_up_locked"]=True
        result=build_execution_table(bars)
        self.assertEqual(result.loc[20,"ENTRY_STATUS"],"UNFILLED")

if __name__=="__main__":
    unittest.main()
