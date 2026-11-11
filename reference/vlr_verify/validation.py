"""Strict daily research input validation; never infer an exchange calendar."""
import numpy as np
import pandas as pd


def daily_dates(values, name="date"):
    try:
        dates = pd.to_datetime(values, errors="raise")
        index = pd.DatetimeIndex(dates)
    except (ValueError, TypeError) as exc:
        raise ValueError(f"Invalid {name}") from exc
    if index.hasnans or index.tz is not None or not index.equals(index.normalize()):
        raise ValueError(f"{name} must contain nonmissing, timezone-naive daily dates")
    return index


def strict_boolean(values, name):
    if values.isna().any() or not values.isin([True, False, 0, 1]).all():
        raise ValueError(f"{name} must contain only nonmissing boolean or 0/1 values")
    return values.astype(bool)


def finite_numeric(values, name, *, minimum=0):
    try:
        numbers = pd.to_numeric(values, errors="raise")
    except (ValueError, TypeError) as exc:
        raise ValueError(f"{name} must be numeric") from exc
    if not np.isfinite(numbers.to_numpy(dtype=float)).all() or (numbers < minimum).any():
        raise ValueError(f"{name} must be finite and >= {minimum}")
    return numbers
