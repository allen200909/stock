"""Moving calendar-block bootstrap of an event-weighted mean.

All events on a session travel together. Empty sessions stay on the calendar.
The caller must provide the complete, predeclared evaluation calendar.
"""
import numpy as np
import pandas as pd
from validation import daily_dates


def block_bootstrap(events, *, trading_calendar, block_lengths=(5, 10, 20),
                    repetitions=2000, seed=20261013, confidence=0.95):
    calendar = daily_dates(trading_calendar, "trading_calendar")
    if calendar.empty or not calendar.is_unique or not calendar.is_monotonic_increasing:
        raise ValueError("Calendar must be sorted, unique and nonempty")
    if not isinstance(repetitions, int) or repetitions < 100:
        raise ValueError("Need >=100 bootstrap repetitions")
    if not 0 < confidence < 1:
        raise ValueError("confidence must be in (0,1)")
    frame = events.copy()
    frame["date"] = daily_dates(frame["date"])
    if frame.empty or not frame.date.isin(calendar).all():
        raise ValueError("Nonempty events must lie within the evaluation calendar")
    values = pd.to_numeric(frame["return"], errors="raise")
    if not np.isfinite(values.to_numpy(dtype=float)).all():
        raise ValueError("Missing returns must be resolved before inference")
    frame["return"] = values
    daily = frame.groupby("date")["return"].agg(["sum", "count"]).reindex(calendar, fill_value=0)
    totals, counts = daily["sum"].to_numpy(), daily["count"].to_numpy()
    lengths = tuple(block_lengths)
    if not lengths or len(set(lengths)) != len(lengths):
        raise ValueError("Supply distinct block lengths")
    output = []
    for length in lengths:
        if not isinstance(length, int) or length < 1 or 2 * length > len(calendar):
            raise ValueError("Each block must be positive and at most half the calendar")
        rng = np.random.default_rng(seed)
        estimates = []
        for _ in range(repetitions):
            starts = rng.integers(0, len(calendar) - length + 1,
                                  size=(len(calendar) + length - 1) // length)
            positions = (starts[:, None] + np.arange(length)).ravel()[:len(calendar)]
            denominator = counts[positions].sum()
            if denominator:
                estimates.append(totals[positions].sum() / denominator)
        # Sparse-event resamples must not silently condition away many empty draws.
        if len(estimates) < 0.95 * repetitions:
            raise ValueError("Too many zero-event bootstrap draws; insufficient event coverage")
        lo, hi = np.quantile(estimates, [(1-confidence)/2, (1+confidence)/2])
        output.append({"block_length":length, "mean":float(values.mean()),
                       "ci_low":float(lo), "ci_high":float(hi),
                       "events":len(frame), "sessions":len(calendar),
                       "valid_draws":len(estimates), "empty_draws":repetitions-len(estimates),
                       "repetitions":repetitions, "seed":seed, "confidence":confidence})
    return pd.DataFrame(output)
