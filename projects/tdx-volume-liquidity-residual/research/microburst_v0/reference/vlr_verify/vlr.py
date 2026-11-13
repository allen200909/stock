"""VLR research replica: frozen B0 and experimental E1–E4.

Not validated against TongDaXin. Never use as trading proof before barwise parity.
Inputs: open, high, low, close, volume; E4 additionally requires amount.
All data must be chronological, one instrument at a time.
"""
from __future__ import annotations

from typing import Literal

import numpy as np
import pandas as pd
from validation import daily_dates, finite_numeric

Model = Literal["B0", "E1", "E2", "E3", "E4"]
DEFAULTS = {
    "N": 60, "ATRN": 14, "VOLN": 20,
    "ZTH": 1.50, "RVVAC": 1.20, "RVTH": 1.50,
    "RVCAP": 3.0, "MVCAP": 4.0, "DTH": 0.25,
    "ATH": 0.10, "CTH": 0.10, "COOL": 3,
    "WDR": 0.50, "WDB": 0.25, "WCV": 0.25,
}


def tdx_sma(values: pd.Series, n: int, *, first: str = "first_valid") -> pd.Series:
    """SMA(X,N,1). Initialization remains a TDX parity question."""
    if first != "first_valid":
        raise ValueError("Only first_valid SMA initialization is implemented")
    arr = values.to_numpy(dtype=float)
    out = np.full(len(arr), np.nan)
    last = np.nan
    for i, value in enumerate(arr):
        if np.isfinite(value):
            last = value if np.isnan(last) else (value + (n - 1) * last) / n
        out[i] = last
    return pd.Series(out, index=values.index)


def mean(values: pd.Series, n: int) -> pd.Series:
    return values.rolling(n, min_periods=n).mean()


def variance(values: pd.Series, n: int) -> pd.Series:
    m = mean(values, n)
    return mean(values * values, n) - m * m


def lagged_z(residual: pd.Series, n: int) -> tuple[pd.Series, pd.Series]:
    old = residual.shift(1)
    mu = mean(old, n)
    sd = old.rolling(n, min_periods=n).std(ddof=1)
    raw_z = ((residual - mu) / sd.where(sd > 0.0001)).fillna(0.0)
    return raw_z, sd


def event(state: pd.Series, cooldown: int) -> pd.Series:
    recent = state.shift(1, fill_value=False).astype(int).rolling(
        cooldown, min_periods=1
    ).sum()
    return state & recent.eq(0)


def calculate(
    df: pd.DataFrame,
    model: Model = "B0",
    *,
    initial_tr: Literal["hl", "missing"] = "hl",
    **overrides: float,
) -> pd.DataFrame:
    """Compute one ticker, without access to future bars.

    initial_tr='hl' follows the prior repository replica; 'missing' is a
    diagnostic for first-bar REF(C,1) semantics, pending actual TDX export.
    """
    if model not in {"B0", "E1", "E2", "E3", "E4"}:
        raise ValueError(f"Unknown model: {model}")
    p = DEFAULTS | overrides
    if any(p[k] <= 0 for k in ["N", "ATRN", "VOLN", "COOL", "RVCAP", "MVCAP"]):
        raise ValueError("All windows, caps and cooldown must be positive")
    required = {"open", "high", "low", "close", "volume"}
    if model == "E4":
        required.add("amount")
    missing = required.difference(df.columns)
    if missing:
        raise ValueError(f"Missing columns: {sorted(missing)}")
    if not df.index.is_monotonic_increasing or not df.index.is_unique:
        raise ValueError("Input index must be unique and chronological")

    if df.empty:
        raise ValueError("Input must not be empty")
    if "date" in df:
        dates = daily_dates(df["date"])
        if not dates.is_unique or not dates.is_monotonic_increasing:
            raise ValueError("Dates must be unique and chronological")
    if "ticker" in df and (df["ticker"].isna().any() or df["ticker"].nunique() != 1):
        raise ValueError("calculate requires exactly one nonmissing ticker")
    for col in required:
        finite_numeric(df[col], col)
    if (df[["open", "high", "low", "close"]].astype(float) <= 0).any().any():
        raise ValueError("Prices must be positive")
    prices = df[["open", "high", "low", "close"]].astype(float)
    if ((prices.high < prices[["open", "close", "low"]].max(axis=1)) |
            (prices.low > prices[["open", "close", "high"]].min(axis=1))).any():
        raise ValueError("Inconsistent OHLC bounds")

    o, h, l, c, v = (df[col].astype(float) for col in
                     ["open", "high", "low", "close", "volume"])
    pc = c.shift(1)
    parts = pd.concat([h - l, (h - pc).abs(), (l - pc).abs()], axis=1)
    tr = parts.max(axis=1, skipna=True)
    if initial_tr == "missing" and len(tr):
        tr.iloc[0] = np.nan
    elif initial_tr != "hl":
        raise ValueError("initial_tr must be 'hl' or 'missing'")
    atrb = tdx_sma(tr, int(p["ATRN"])).shift(1)
    trok = atrb.gt(0.0001)
    mov = (tr / atrb.where(trok)).where(trok, 0.0).fillna(0.0)

    measure = df["amount"].astype(float) if model == "E4" else v
    basis = mean(measure, int(p["VOLN"])).shift(1)
    vok = basis.gt(0)
    rvraw = (measure / basis.where(vok)).where(vok, 1.0).fillna(1.0)
    xfit = rvraw.clip(upper=p["RVCAP"])
    yfit = mov.clip(upper=p["MVCAP"])
    n = int(p["N"])

    if model in {"E2", "E3"}:
        current_x = np.log(xfit.clip(lower=0.05))
        current_y = np.log(yfit.clip(lower=0.05))
    else:
        current_x, current_y = xfit, yfit

    x, y = current_x.shift(1), current_y.shift(1)
    mx, my = mean(x, n), mean(y, n)
    vx, vy = variance(x, n), variance(y, n)
    cov = mean(x * y, n) - mx * my
    slope = (cov / vx.where(vx > 0.0001)).clip(lower=0).fillna(0.0)
    intercept = my - slope * mx
    rho = (cov / np.sqrt(vx.where(vx > 0.0001) *
                         vy.where(vy > 0.0001))).fillna(0.0)

    if model in {"E2", "E3"}:
        residual = np.log(mov.clip(lower=0.05)) - (
            intercept + slope * current_x)
        expect = np.exp(intercept + slope * current_x)
    else:
        expect = (intercept + slope * xfit).clip(lower=0)
        residual = mov - expect

    if model == "E3":
        ar = residual.abs().shift(1)
        mar = mean(ar, n)
        kscale = ((mean(x * ar, n) - mx * mar) /
                  vx.where(vx > 0.0001)).fillna(0.0)
        scale = (mar + kscale * (current_x - mx)).clip(lower=0.05)
        standardized = residual / scale
        raw_z, sd = lagged_z(standardized, n)
        warm_n = 3 * n + max(int(p["ATRN"]), int(p["VOLN"])) + 5
    else:
        scale = pd.Series(np.nan, index=df.index)
        raw_z, sd = lagged_z(residual, n)
        warm_n = 2 * n + max(int(p["ATRN"]), int(p["VOLN"])) + 5

    valid = pd.Series(np.arange(1, len(df) + 1) > warm_n, index=df.index)
    valid &= trok & vok & sd.gt(0.0001)
    z = raw_z.where(valid, 0.0)

    trb = tr.clip(lower=0.001)
    dr, db = (c - pc) / trb, (c - o) / trb
    clv = ((2 * c - h - l) / (h - l).where(h > l)).fillna(0.0)
    weight_sum = max(p["WDR"] + p["WDB"] + p["WCV"], 0.0001)
    direction = (p["WDR"] * dr + p["WDB"] * db +
                 p["WCV"] * clv) / weight_sum

    jumbo = rvraw > p["RVCAP"]
    ordinary = (~jumbo) if model in {"E1", "E2", "E3"} else pd.Series(
        True, index=df.index
    )
    positive = valid & ordinary & z.gt(p["ZTH"])
    negative = valid & ordinary & z.lt(-p["ZTH"])
    long_move, short_move = direction.gt(p["DTH"]), direction.lt(-p["DTH"])
    states = {
        "VU0": positive & long_move & rvraw.lt(p["RVVAC"]),
        "VD0": positive & short_move & rvraw.lt(p["RVVAC"]),
        "EU0": positive & long_move & rvraw.ge(p["RVVAC"]),
        "ED0": positive & short_move & rvraw.ge(p["RVVAC"]),
        "ABU0": negative & rvraw.gt(p["RVTH"]) &
                direction.gt(p["ATH"]) & clv.gt(p["CTH"]),
        "ABD0": negative & rvraw.gt(p["RVTH"]) &
                direction.lt(-p["ATH"]) & clv.lt(-p["CTH"]),
    }
    result = pd.DataFrame({
        "MOV": mov, "RVRAW": rvraw, "EXPECT": expect, "RES": residual,
        "Z": z, "DIR": direction, "CLV": clv, "RHO": rho,
        "R2RAW": rho * rho, "R2POS": rho.clip(lower=0) ** 2,
        "SC": scale, "JUMBO": jumbo, "VALID": valid,
    }, index=df.index)
    for name, state in states.items():
        result[name] = state.fillna(False)
        result[name.removesuffix("0")] = event(result[name], int(p["COOL"]))

    if model == "E1":
        ju0 = valid & jumbo & direction.gt(p["DTH"])
        jd0 = valid & jumbo & direction.lt(-p["DTH"])
        result["JU0"], result["JD0"] = ju0, jd0
        result["JU"], result["JD"] = (
            event(ju0, int(p["COOL"])), event(jd0, int(p["COOL"])))
    return add_selectors(result)


def add_selectors(frame: pd.DataFrame) -> pd.DataFrame:
    """The TDX selection and eight mutually exclusive activity states."""
    out = frame.copy()
    eu = out["EU"].astype(bool)
    for n in (3, 10, 20, 60):
        out[f"CNT{n}"] = eu.astype(int).rolling(n, min_periods=1).sum().astype(int)
    c60, c20, c10 = out["CNT60"], out["CNT20"], out["CNT10"]
    hot = (c10 >= 3) | (c20 >= 4)
    quiet = (c60 <= 1) & ~hot
    warmup = (c60 == 2) & (c10 >= 1) & ~hot
    active = c60.between(3, 4) & c10.between(1, 2) & ~hot
    highact = c60.between(5, 6) & c10.between(1, 2) & ~hot
    longact = (c60 >= 7) & c10.between(1, 2) & (c20 <= 3) & ~hot
    fading = (c60 >= 2) & (c10 == 0) & ~hot
    states = {
        "HOT": hot, "QUIET": quiet, "WARMUP": warmup,
        "ACTIVE": active, "HIGHACT": highact, "LONGACT": longact,
        "FADING": fading,
    }
    states["OTHER"] = ~pd.concat(states.values(), axis=1).any(axis=1)
    for name, value in states.items():
        out[name] = value.astype(bool)
    out["XG3"] = out["CNT3"] >= 1
    out["XG6010"] = (c60 >= 3) & (c10 >= 1)
    out["XGLAYER"] = active | highact
    return out


# Backwards-compatible alias (previous verify scripts import calc).
calc = calculate
