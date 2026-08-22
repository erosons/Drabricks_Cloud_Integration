"""Vectorized indicators for the card strategies (§8 playbook).

All functions take the bar DataFrame (OHLCV, UTC index) and return Series/
DataFrames aligned to it. Confirmation-lagged constructs (fractals, swing
pivots) are shifted so a value at bar i was KNOWABLE at bar i — no
lookahead; that discipline is the whole point of the research plane.
"""

from __future__ import annotations

import numpy as np
import pandas as pd


def sma(s: pd.Series, n: int) -> pd.Series:
    return s.rolling(n).mean()


def ema(s: pd.Series, n: int) -> pd.Series:
    return s.ewm(span=n, adjust=False).mean()


def rsi(close: pd.Series, n: int = 14) -> pd.Series:
    delta = close.diff()
    gain = delta.clip(lower=0).ewm(alpha=1 / n, adjust=False).mean()
    loss = (-delta.clip(upper=0)).ewm(alpha=1 / n, adjust=False).mean()
    out = 100 - 100 / (1 + gain / loss.replace(0, np.nan))
    out[(loss == 0) & (gain > 0)] = 100.0     # pure advance
    return out.fillna(50.0)                   # flat / warmup


def atr(df: pd.DataFrame, n: int = 14) -> pd.Series:
    prev_close = df["close"].shift()
    tr = pd.concat([df["high"] - df["low"],
                    (df["high"] - prev_close).abs(),
                    (df["low"] - prev_close).abs()], axis=1).max(axis=1)
    return tr.ewm(alpha=1 / n, adjust=False).mean()


def bollinger(close: pd.Series, n: int = 20, k: float = 2.0) -> pd.DataFrame:
    mid = close.rolling(n).mean()
    sd = close.rolling(n).std(ddof=0)
    return pd.DataFrame({"bb_mid": mid, "bb_up": mid + k * sd,
                         "bb_dn": mid - k * sd,
                         "bb_width": (2 * k * sd) / mid})


def rolling_percentile(s: pd.Series, lookback: int) -> pd.Series:
    """Percentile rank (0-100) of each value within its trailing window."""
    return s.rolling(lookback).rank(pct=True) * 100


def donchian(df: pd.DataFrame, n: int = 20) -> pd.DataFrame:
    hi = df["high"].rolling(n).max()
    lo = df["low"].rolling(n).min()
    return pd.DataFrame({"dc_hi": hi, "dc_lo": lo, "dc_mid": (hi + lo) / 2})


def supertrend(df: pd.DataFrame, atr_period: int = 10,
               mult: float = 3.0) -> pd.DataFrame:
    """Classic Supertrend: line + direction (+1 up / −1 down), bar-close."""
    a = atr(df, atr_period)
    hl2 = (df["high"] + df["low"]) / 2
    up_base = (hl2 + mult * a).to_numpy()
    dn_base = (hl2 - mult * a).to_numpy()
    close = df["close"].to_numpy()
    n = len(df)
    line = np.full(n, np.nan)
    direction = np.zeros(n)
    up, dn, d = up_base[0], dn_base[0], 1
    for i in range(n):
        up = min(up_base[i], up) if close[i - 1] <= up else up_base[i]
        dn = max(dn_base[i], dn) if close[i - 1] >= dn else dn_base[i]
        if d == 1 and close[i] < dn:
            d = -1
        elif d == -1 and close[i] > up:
            d = 1
        line[i] = dn if d == 1 else up
        direction[i] = d
    return pd.DataFrame({"st_line": line, "st_dir": direction},
                        index=df.index)


def psar(df: pd.DataFrame, af_step: float = 0.02,
         af_max: float = 0.2) -> pd.DataFrame:
    """Parabolic SAR: dot + direction (+1 long dots below / −1 short)."""
    high, low = df["high"].to_numpy(), df["low"].to_numpy()
    n = len(df)
    sar = np.full(n, np.nan)
    direction = np.zeros(n)
    d, ep, af = 1, high[0], af_step
    cur = low[0]
    for i in range(1, n):
        cur = cur + af * (ep - cur)
        if d == 1:
            cur = min(cur, low[i - 1], low[i - 2] if i > 1 else low[i - 1])
            if low[i] < cur:
                d, cur, ep, af = -1, ep, low[i], af_step
            elif high[i] > ep:
                ep, af = high[i], min(af + af_step, af_max)
        else:
            cur = max(cur, high[i - 1], high[i - 2] if i > 1 else high[i - 1])
            if high[i] > cur:
                d, cur, ep, af = 1, ep, high[i], af_step
            elif low[i] < ep:
                ep, af = low[i], min(af + af_step, af_max)
        sar[i] = cur
        direction[i] = d
    return pd.DataFrame({"sar": sar, "sar_dir": direction}, index=df.index)


def session_vwap(df: pd.DataFrame) -> pd.DataFrame:
    """Session-anchored VWAP + 1σ/2σ bands (volume-weighted variance),
    anchored on `session_date` (add_session_columns first)."""
    tp = (df["high"] + df["low"] + df["close"]) / 3
    pv = tp * df["volume"]
    grp = df.groupby("session_date", sort=False)
    cum_v = grp["volume"].cumsum()
    cum_pv = pv.groupby(df["session_date"]).cumsum()
    vwap = cum_pv / cum_v.replace(0, np.nan)
    cum_p2v = (tp * tp * df["volume"]).groupby(df["session_date"]).cumsum()
    var = (cum_p2v / cum_v.replace(0, np.nan)) - vwap * vwap
    sd = np.sqrt(var.clip(lower=0))
    return pd.DataFrame({"vwap": vwap, "vwap_sd": sd})


def daily_pivots(df: pd.DataFrame) -> pd.DataFrame:
    """Traditional floor pivots + CPR from the PRIOR session's OHLC,
    constant across each session (uses `session_date`)."""
    daily = df.groupby("session_date").agg(
        H=("high", "max"), L=("low", "min"), C=("close", "last"))
    prior = daily.shift(1)
    p = (prior["H"] + prior["L"] + prior["C"]) / 3
    out = pd.DataFrame({
        "P": p,
        "R1": 2 * p - prior["L"], "S1": 2 * p - prior["H"],
        "R2": p + (prior["H"] - prior["L"]),
        "S2": p - (prior["H"] - prior["L"]),
        "BC": (prior["H"] + prior["L"]) / 2,
    })
    out["TC"] = 2 * p - out["BC"]
    out["cpr_width"] = (out["TC"] - out["BC"]).abs()
    return out.reindex(df["session_date"]).set_index(df.index)


def fractals(df: pd.DataFrame, wing: int = 2) -> pd.DataFrame:
    """Bill Williams fractals, CONFIRMED only: a fractal at bar k needs
    `wing` bars each side, so it becomes knowable at k+wing — values here
    are the last confirmed fractal as of each bar (ffilled, no lookahead)."""
    hi, lo = df["high"], df["low"]
    up = hi[(hi == hi.rolling(2 * wing + 1, center=True).max())]
    dn = lo[(lo == lo.rolling(2 * wing + 1, center=True).min())]
    up_conf = up.reindex(df.index).shift(wing).ffill()
    dn_conf = dn.reindex(df.index).shift(wing).ffill()
    return pd.DataFrame({"fractal_up": up_conf, "fractal_dn": dn_conf})


def swing_pivots(df: pd.DataFrame, wing: int = 3) -> pd.DataFrame:
    """Confirmed swing highs/lows (structure engine's bar-based analogue):
    last two of each as of every bar, confirmation-shifted."""
    hi, lo = df["high"], df["low"]
    ph = hi[(hi == hi.rolling(2 * wing + 1, center=True).max())]
    pl = lo[(lo == lo.rolling(2 * wing + 1, center=True).min())]
    ph = ph.reindex(df.index).shift(wing)
    pl = pl.reindex(df.index).shift(wing)
    out = pd.DataFrame(index=df.index)
    out["swing_hi"] = ph.ffill()
    out["swing_hi_prev"] = ph.dropna().shift(1).reindex(df.index).ffill()
    out["swing_lo"] = pl.ffill()
    out["swing_lo_prev"] = pl.dropna().shift(1).reindex(df.index).ffill()
    return out


def rvol_baseline(df: pd.DataFrame, lookback_days: int = 20) -> pd.Series:
    """Same-time-of-day volume baseline (intraday volume is U-shaped):
    mean volume of this minute-of-day over the prior `lookback_days`
    sessions, shifted one session so today never sees itself."""
    mod = df.index.tz_convert("America/New_York")
    key = mod.hour * 60 + mod.minute
    tmp = pd.DataFrame({"volume": df["volume"].values, "key": key,
                        "date": df["session_date"].values})
    piv = tmp.pivot_table(index="date", columns="key", values="volume",
                          aggfunc="sum")
    base = piv.rolling(lookback_days, min_periods=5).mean().shift(1)
    lut = base.stack()
    idx = pd.MultiIndex.from_arrays([tmp["date"], tmp["key"]])
    return pd.Series(lut.reindex(idx).values, index=df.index,
                     name="rvol_baseline")


def regression_channel(close: pd.Series, n: int = 50) -> pd.DataFrame:
    """Rolling linear-regression mid line ± max deviation over the window
    (deterministic trendline substitute, playbook skill 30)."""
    x = np.arange(n)
    x_mean = x.mean()
    denom = ((x - x_mean) ** 2).sum()

    def endpoint(win):
        slope = ((x - x_mean) * (win - win.mean())).sum() / denom
        mid = win.mean() + slope * (n - 1 - x_mean)
        resid = win - (win.mean() + slope * (x - x_mean))
        return mid, np.abs(resid).max()

    mids = np.full(len(close), np.nan)
    devs = np.full(len(close), np.nan)
    vals = close.to_numpy()
    for i in range(n - 1, len(close)):
        mids[i], devs[i] = endpoint(vals[i - n + 1:i + 1])
    return pd.DataFrame({"reg_mid": mids, "reg_up": mids + devs,
                         "reg_dn": mids - devs}, index=close.index)
