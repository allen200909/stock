"""Regression cases for review findings; replica exports only test the gate."""
import unittest
import numpy as np
import pandas as pd
from test_synthetic import sample
from vlr import calculate
from execution import build_execution_table
from tdx_parity import compare, NUMERIC, BOOLEAN


def bars():
    return pd.DataFrame({"date":pd.bdate_range("2026-01-01", periods=30),
        "ticker":"T", "RAW_SIGNAL":1.0, "amount":100_000_000,
        "is_st":False, "listing_age_days":300, "suspended":False,
        "limit_up_locked":False, "limit_down_locked":False})


def aligned():
    df=sample(200)
    df["date"]=pd.bdate_range("2025-01-01",periods=len(df))
    result=calculate(df)
    for key,col in (NUMERIC | BOOLEAN).items():
        df[col]=result[key].astype(float)
    return df


class ValidationTests(unittest.TestCase):
    def test_parity_valid_and_mismatch(self):
        df=aligned()
        self.assertTrue(all(r["pass"] for r in compare(df).values()))
        self.assertTrue(all(r["compared_bars"]==55 for r in compare(df).values()))
        df.loc[199,"TDX_EU"]=1-df.loc[199,"TDX_EU"]
        self.assertFalse(compare(df)["EU"]["pass"])

    def test_parity_missing_or_invalid(self):
        for col in (NUMERIC | BOOLEAN).values():
            for value in [np.nan, np.inf, "bad"]:
                with self.subTest(col=col,value=value):
                    df=aligned(); df[col]=df[col].astype(object)
                    df.loc[199,col]=value
                    with self.assertRaises(ValueError): compare(df)
        for col in BOOLEAN.values():
            df=aligned(); df[col]=np.nan
            with self.assertRaises(ValueError): compare(df)
            df=aligned(); df.loc[199,col]=2
            with self.assertRaises(ValueError): compare(df)
        with self.assertRaises(ValueError): compare(aligned().iloc[:145])
        with self.assertRaises(ValueError): compare(aligned(), tolerance=-1)

    def test_signal_and_flags_reject_invalid(self):
        for col in ["RAW_SIGNAL","is_st","suspended","limit_up_locked","limit_down_locked"]:
            for value in [np.nan,"False",2]:
                df=bars(); df[col]=df[col].astype(object); df.loc[20,col]=value
                with self.subTest(col=col,value=value), self.assertRaises(ValueError):
                    build_execution_table(df,trading_calendar=bars().date)

    def test_next_session_missing_and_locked(self):
        df=bars(); calendar=df.date
        result=build_execution_table(df.drop(index=[21,22]),trading_calendar=calendar)
        row=result.loc[result.date.eq(df.loc[20,"date"])].iloc[0]
        self.assertEqual(row.ENTRY_DATE,df.loc[21,"date"])
        self.assertEqual(row.ENTRY_STATUS,"DATA_MISSING")
        # Missing history also invalidates a 20-session liquidity average.
        self.assertTrue(result.loc[result.date.eq(df.loc[23,"date"]),"amt20"].isna().all())
        for col in ["suspended","limit_up_locked"]:
            df=bars(); df.loc[21,col]=True
            self.assertEqual(build_execution_table(df,trading_calendar=calendar).loc[20,"ENTRY_STATUS"],"UNFILLED")
        self.assertEqual(build_execution_table(bars(),trading_calendar=calendar).iloc[-1].ENTRY_STATUS,"PENDING")

    def test_calendar_holiday_and_ticker_isolation(self):
        df=bars().drop(index=21); calendar=df.date
        other=df.copy(); other["ticker"]="U"; other["limit_up_locked"]=True
        result=build_execution_table(pd.concat([df,other]),trading_calendar=calendar)
        row=result.loc[result.ticker.eq("T") & result.date.eq(df.loc[20,"date"])].iloc[0]
        self.assertEqual(row.ENTRY_DATE,df.loc[22,"date"])
        self.assertEqual(row.ENTRY_STATUS,"ELIGIBLE_FOR_FILL_CHECK")
        with self.assertRaises(ValueError):
            build_execution_table(pd.concat([df,df.iloc[:1]]),trading_calendar=calendar)
        with self.assertRaises(ValueError):
            build_execution_table(df,trading_calendar=calendar.iloc[::-1])

    def test_chronology_and_price_validation(self):
        for kind in ["reverse","duplicate","mixed","nan","ohlc"]:
            df=sample(200); df["date"]=pd.bdate_range("2025-01-01",periods=200)
            if kind=="reverse": df["date"]=df.date.iloc[::-1].to_numpy()
            if kind=="duplicate": df.loc[199,"date"]=df.loc[198,"date"]
            if kind=="mixed": df["ticker"]=["A"]*199+["B"]
            if kind=="nan": df.loc[199,"volume"]=np.nan
            if kind=="ohlc": df.loc[199,"high"]=0.01
            with self.subTest(kind=kind), self.assertRaises(ValueError): calculate(df)

if __name__=="__main__": unittest.main()
