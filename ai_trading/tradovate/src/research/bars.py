"""Tick → bar cache for the research plane (§9).

Aggregates Databento TBBO monthly files into 1-minute OHLCV bars once per
product (vectorized, ~minutes for a year) and caches them as parquet;
higher timeframes are resampled from the 1m cache on demand. Bars carry
buy/sell aggressor volume so volume-based cards keep their tape signal.

The cache lives next to the data it came from:
    data/databento/bars_{PRODUCT}_1m.parquet
"""

from __future__ import annotations

from pathlib import Path

import pandas as pd

from src.utils.logger import get_logger

log = get_logger("bars")


def build_bar_cache(data_dir: str | Path, product: str,
                    out_dir: str | Path | None = None) -> Path:
    """One-time (idempotent) tick→1m aggregation for every monthly TBBO
    file in `data_dir`. Returns the parquet path."""
    import databento as db

    data_dir = Path(data_dir)
    out_dir = Path(out_dir) if out_dir else data_dir.parent
    out = out_dir / f"bars_{product}_1m.parquet"
    if out.exists():
        log.info("bar cache exists: %s", out)
        return out

    frames = []
    for f in sorted(data_dir.glob("*.tbbo.dbn.zst")):
        log.info("aggregating %s", f.name)
        for df in db.DBNStore.from_file(f).to_df(count=4_000_000):
            df = df[df["side"] != "N"]
            g = df.groupby(pd.Grouper(freq="1min", level="ts_recv"))
            bar = g["price"].ohlc()
            bar["volume"] = g["size"].sum()
            buys = df[df["side"] == "B"].groupby(
                pd.Grouper(freq="1min", level="ts_recv"))["size"].sum()
            bar["buy_volume"] = buys.reindex(bar.index).fillna(0)
            bar["sell_volume"] = bar["volume"] - bar["buy_volume"]
            frames.append(bar.dropna(subset=["open"]))
    bars = pd.concat(frames)
    # chunk boundaries can split a minute across frames — merge duplicates
    bars = bars.groupby(level=0).agg(
        open=("open", "first"), high=("high", "max"), low=("low", "min"),
        close=("close", "last"), volume=("volume", "sum"),
        buy_volume=("buy_volume", "sum"), sell_volume=("sell_volume", "sum"))
    bars.index.name = "ts"
    bars.to_parquet(out)
    log.info("bar cache: %d 1m bars → %s", len(bars), out)
    return out


def load_bars(product: str, timeframe_min: int,
              cache_dir: str | Path = "data/databento",
              date_from: str | None = None,
              date_to: str | None = None) -> pd.DataFrame:
    """Load the 1m cache and resample to `timeframe_min`. Bars are labeled
    by OPEN time; a bar is 'closed' once the next one begins."""
    path = Path(cache_dir) / f"bars_{product}_1m.parquet"
    df = pd.read_parquet(path)
    if date_from:
        df = df[df.index >= pd.Timestamp(date_from, tz="UTC")]
    if date_to:
        df = df[df.index < pd.Timestamp(date_to, tz="UTC")
                + pd.Timedelta(days=1)]
    if timeframe_min != 1:
        g = df.resample(f"{timeframe_min}min")
        df = pd.DataFrame({
            "open": g["open"].first(), "high": g["high"].max(),
            "low": g["low"].min(), "close": g["close"].last(),
            "volume": g["volume"].sum(),
            "buy_volume": g["buy_volume"].sum(),
            "sell_volume": g["sell_volume"].sum(),
        }).dropna(subset=["open"])
    return df


def add_session_columns(df: pd.DataFrame, session_cfg: dict) -> pd.DataFrame:
    """Annotate bars with the trading session (§6): `in_session` for the
    entry window, `flatten` from (close − buffer) onward, `session_date`
    for session-anchored indicators (VWAP, pivots)."""
    tz = session_cfg["timezone"]
    local = df.index.tz_convert(tz)
    open_h, open_m = map(int, session_cfg["open"].split(":"))
    close_h, close_m = map(int, session_cfg["close"].split(":"))
    buffer_min = int(session_cfg["flatten_buffer_minutes"])
    minutes = local.hour * 60 + local.minute
    open_min = open_h * 60 + open_m
    close_min = close_h * 60 + close_m
    day_ok = local.strftime("%a").isin(list(session_cfg["trade_days"]))
    out = df.copy()
    out["in_session"] = day_ok & (minutes >= open_min) & (minutes < close_min)
    out["flatten"] = day_ok & (minutes >= close_min - buffer_min)
    out["session_date"] = local.date
    out["minutes_since_open"] = minutes - open_min
    return out
