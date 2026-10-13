import copy
from datetime import datetime, timedelta, timezone
from pathlib import Path
import tempfile
import unittest
import numpy as np
import pandas as pd
from confirmation import freeze
from inference import block_bootstrap
from trade_study import simulate_events
from test_validation import bars, aligned
from tdx_parity import compare, BOOLEAN


class ResearchTests(unittest.TestCase):
    def test_all_parity_outputs_and_legacy_scope(self):
        df = aligned()
        for col in BOOLEAN.values():
            broken = df.copy()
            broken.loc[199, col] = 1 - broken.loc[199, col]
            self.assertFalse(compare(broken)[col.removeprefix("TDX_")]["pass"])
        old = df.drop(columns="TDX_ABD")
        with self.assertRaises(ValueError): compare(old)
        self.assertTrue(all(r["pass"] for r in compare(old, scope="core").values()))

    def test_bootstrap_constant_cross_section_and_seed(self):
        calendar = pd.bdate_range("2025-01-01", periods=80)
        events = pd.DataFrame({"date":np.repeat(calendar, 2), "return":np.tile([0., .04], 80)})
        result = block_bootstrap(events, trading_calendar=calendar, repetitions=100)
        np.testing.assert_allclose(result[["mean", "ci_low", "ci_high"]], .02)
        events["return"] = np.arange(len(events)) / 1000
        a = block_bootstrap(events, trading_calendar=calendar, repetitions=100)
        b = block_bootstrap(events, trading_calendar=calendar, repetitions=100)
        pd.testing.assert_frame_equal(a, b)
        events.loc[0,"return"] = np.nan
        with self.assertRaises(ValueError): block_bootstrap(events, trading_calendar=calendar)

    def test_bootstrap_keeps_empty_sessions_and_rejects_sparse_draws(self):
        calendar = pd.bdate_range("2025-01-01", periods=80)
        events = pd.DataFrame({"date":calendar[::2], "return":.01})
        result = block_bootstrap(events, trading_calendar=calendar, repetitions=100)
        self.assertTrue(result.sessions.eq(80).all())
        self.assertTrue(result.events.eq(40).all())
        with self.assertRaises(ValueError):
            block_bootstrap(events.iloc[:1], trading_calendar=calendar, repetitions=100)
        with self.assertRaises(ValueError):
            block_bootstrap(events, trading_calendar=calendar, block_lengths=[41])

    def fixture(self):
        df = bars()
        df["RAW_SIGNAL"] = False
        df.loc[20,"RAW_SIGNAL"] = True
        df["open"] = 10.0
        df["open_buyable"] = True
        df["open_sellable"] = True
        return df

    def simulate(self, df, calendar=None, **kwargs):
        options = dict(trading_calendar=df.date if calendar is None else calendar,
                       holding_sessions=1, buy_cost_bps=10, sell_cost_bps=20,
                       slippage_bps=5, price_convention="synthetic unadjusted; no corporate actions")
        return simulate_events(df, **(options | kwargs))

    def test_trade_costs_timing_and_exit_deferral(self):
        df = self.fixture()
        df.loc[22,"limit_down_locked"] = True
        df.loc[23,"open_sellable"] = False
        df.loc[24,"open"] = 11.0
        result = self.simulate(df).iloc[0]
        self.assertEqual(result.status,"SIMULATED_CLOSED")
        self.assertEqual(result.entry_date,df.loc[21,"date"])
        self.assertEqual(result.exit_date,df.loc[24,"date"])
        self.assertEqual(result.exit_delay_sessions,2)
        self.assertAlmostEqual(result.gross_return,.1)
        self.assertAlmostEqual(result.net_return,11*(1-.0005)*(1-.002)/(10*(1+.0005)*(1+.001))-1)
        with self.assertRaises(ValueError): self.simulate(df,holding_sessions=0)
        with self.assertRaises(ValueError): self.simulate(df,buy_cost_bps=-1)

    def test_trade_unfilled_missing_censored_and_empty(self):
        df = self.fixture(); df.loc[21,"open_buyable"] = False
        self.assertEqual(self.simulate(df).iloc[0].status,"UNFILLED_OPEN")
        df = self.fixture()
        self.assertEqual(self.simulate(df.drop(index=22),calendar=df.date).iloc[0].status,"EXIT_DATA_MISSING")
        self.assertEqual(self.simulate(df,holding_sessions=20).iloc[0].status,"OPEN_CENSORED")
        self.assertTrue(pd.isna(self.simulate(df,holding_sessions=20).iloc[0].net_return))
        df["RAW_SIGNAL"] = False
        self.assertTrue(self.simulate(df).empty)

    def test_registration_write_once_and_no_retroactive_holdout(self):
        start = (datetime.now(timezone.utc)+timedelta(days=2)).date().isoformat()
        spec = dict(code_commit="a"*40, data_source_version="fixture-v1", universe="fixture",
                    price_convention="fixture", parameters={"N":60}, cost_assumptions={"bps":10},
                    prior_data_exposure="fixture only", confirmation_start=start,
                    confirmation_end=start, primary_metric="mean net event return",
                    acceptance_rule="predeclared fixture criterion", block_lengths=[5,10,20],
                    outcomes_previously_viewed=False)
        with tempfile.TemporaryDirectory() as root:
            target = Path(root)/"registration.json"
            report = freeze(spec,target)
            self.assertEqual(report["status"],"REGISTERED_NOT_EVALUATED")
            with self.assertRaises(FileExistsError): freeze(spec,target)
            bad = copy.deepcopy(spec); bad["outcomes_previously_viewed"] = True
            with self.assertRaises(ValueError): freeze(bad,Path(root)/"bad.json")
            bad = copy.deepcopy(spec); bad["confirmation_start"] = "2021-01-01"
            with self.assertRaises(ValueError): freeze(bad,Path(root)/"bad.json")


if __name__ == "__main__": unittest.main()
