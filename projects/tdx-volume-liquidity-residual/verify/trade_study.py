"""Independent-event open-price simulation, not a capital-constrained portfolio.

Requires historical opening-auction executability supplied by the data provider.
No order queue or partial-fill behavior is inferred from daily OHLC bars.
"""
import numpy as np
import pandas as pd
from execution import build_execution_table
from validation import daily_dates, strict_boolean, finite_numeric


def simulate_events(bars, *, trading_calendar, holding_sessions,
                    buy_cost_bps, sell_cost_bps, slippage_bps, price_convention,
                    min_turnover=50_000_000, min_listing_days=250):
    if not isinstance(holding_sessions, int) or holding_sessions < 1:
        raise ValueError("holding_sessions must be >=1 (no entry-day exit)")
    costs = np.array([buy_cost_bps, sell_cost_bps, slippage_bps], dtype=float)
    if not np.isfinite(costs).all() or (costs < 0).any() or (costs >= 10000).any():
        raise ValueError("Costs must be finite bps in [0,10000)")
    if not isinstance(price_convention, str) or not price_convention.strip():
        raise ValueError("Document return-consistent price/corporate-action convention")
    df = bars.copy()
    for col in ["open_buyable", "open_sellable"]:
        df[col] = strict_boolean(df[col], col)
    df["open"] = finite_numeric(df["open"], "open")
    if (df.open <= 0).any():
        raise ValueError("Open prices must be positive, including supplied suspension marks")
    table = build_execution_table(df, trading_calendar=trading_calendar,
                                 min_turnover=min_turnover, min_listing_days=min_listing_days)
    calendar = daily_dates(trading_calendar)
    quotes = table.set_index(["ticker", "date"])
    rows = []
    for signal in table.loc[table.RAW_SIGNAL].itertuples():
        record = {"ticker":signal.ticker, "signal_date":signal.date,
                  "entry_date":signal.ENTRY_DATE, "exit_date":pd.NaT,
                  "status":signal.ENTRY_STATUS, "gross_return":np.nan,
                  "net_return":np.nan, "exit_delay_sessions":0,
                  "holding_sessions":holding_sessions,
                  "buy_cost_bps":buy_cost_bps, "sell_cost_bps":sell_cost_bps,
                  "slippage_bps":slippage_bps, "price_convention":price_convention}
        rows.append(record)
        if signal.ENTRY_STATUS != "ELIGIBLE_FOR_FILL_CHECK":
            continue
        entry = quotes.loc[(signal.ticker, signal.ENTRY_DATE)]
        if not entry.open_buyable:
            record["status"] = "UNFILLED_OPEN"
            continue
        target = calendar.get_loc(signal.ENTRY_DATE) + holding_sessions
        record["status"] = "OPEN_CENSORED"
        # Examine all holding sessions too: missing bars are not silently bridged.
        for position in range(calendar.get_loc(signal.ENTRY_DATE)+1, len(calendar)):
            key = (signal.ticker, calendar[position])
            if key not in quotes.index:
                record["status"] = "EXIT_DATA_MISSING"
                break
            if position < target:
                continue
            quote = quotes.loc[key]
            if quote.suspended or quote.limit_down_locked or not quote.open_sellable:
                record["exit_delay_sessions"] += 1
                continue
            record["status"] = "SIMULATED_CLOSED"
            record["exit_date"] = calendar[position]
            record["gross_return"] = quote.open / entry.open - 1
            paid = entry.open * (1 + slippage_bps/10000) * (1 + buy_cost_bps/10000)
            received = quote.open * (1 - slippage_bps/10000) * (1 - sell_cost_bps/10000)
            record["net_return"] = received / paid - 1
            break
    columns = ["ticker", "signal_date", "entry_date", "exit_date", "status",
               "gross_return", "net_return", "exit_delay_sessions", "holding_sessions",
               "buy_cost_bps", "sell_cost_bps", "slippage_bps", "price_convention"]
    return pd.DataFrame(rows, columns=columns)
