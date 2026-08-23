"""Bar-level implementations of the playbook cards (§8) for G2 testing.

One class per card, faithful to the card's mechanics at bar resolution;
where a card's rule needed a bar-level interpretation, the choice is
recorded in the class `notes` (persisted with every run) so results are
reproducible and honest. `sector_confirmation` is a gate, not a
standalone strategy — it has no class here and is recorded as such by
the runner.

Common contract (driven by bar_backtester.BarBracketSim):
  prepare(df)       add indicator columns / arrays (vectorized, no lookahead)
  on_bar(df, i)     closed bar i, only called flat+in-session → Entry | None
  manage(df, i, pos) closed-bar management → "exit" | new stop float | None
"""

from __future__ import annotations

import numpy as np

from src.research import indicators as ind
from src.research.bar_backtester import Entry

TICK_EPS = 1e-9


class CardStrategy:
    name = "base"
    timeframe_min = 15
    notes = ""

    def __init__(self, params: dict, product):
        self.p = params
        self.product = product
        self.tick = product.tick_size
        self.a: dict[str, np.ndarray] = {}

    def _cols(self, df, **series) -> None:
        for key, s in series.items():
            df[key] = s
            self.a[key] = df[key].to_numpy()
        for key in ("open", "high", "low", "close", "volume",
                    "minutes_since_open"):
            if key in df and key not in self.a:
                self.a[key] = df[key].to_numpy()

    def prepare(self, df):
        return df

    def on_bar(self, df, i):
        return None

    def manage(self, df, i, pos):
        return None


# -------------------------------------------------- data-derived (2026-08)

class OpeningRange(CardStrategy):
    name = "opening_range"
    timeframe_min = 5
    notes = ("range = first or_window_minutes of RTH; entry = first 5m "
             "close beyond boundary ± buffer, market next bar; no entry "
             "before 08:45 ET (news rule, declared on card); one-and-done "
             "per session; quality filter 1.0-6.0 × ATR; in-sample-origin "
             "honesty clause on card — holdout is the verdict")

    def prepare(self, df):
        window = int(self.p["or_window_minutes"])
        self.entry_earliest = max(window, 45)          # card news rule
        self.cutoff = int(self.p["entry_cutoff_min"])
        in_window = df["minutes_since_open"].between(0, window - 1) \
            & df["in_session"]
        grp = df["session_date"]
        or_hi = df["high"].where(in_window).groupby(grp).transform("max")
        or_lo = df["low"].where(in_window).groupby(grp).transform("min")
        # ATR frozen at the last window bar: the session-quality decision
        # and the buffer are made ONCE — the breakout bar must not be able
        # to move its own goalposts
        atr = ind.atr(df)
        or_atr = atr.where(in_window).groupby(grp).transform("last")
        self._cols(df, or_hi=or_hi, or_lo=or_lo, atr=or_atr)
        self.sess = df["session_date"].to_numpy()
        self._day = None
        self._done = False
        return df

    def on_bar(self, df, i):
        a = self.a
        if self.sess[i] != self._day:
            self._day, self._done = self.sess[i], False
        if self._done:
            return None
        mins = a["minutes_since_open"][i]
        if not (self.entry_earliest <= mins < self.cutoff):
            return None
        hi, lo, atr = a["or_hi"][i], a["or_lo"][i], a["atr"][i]
        if np.isnan(hi) or np.isnan(lo) or np.isnan(atr) or atr <= 0:
            return None
        rng = hi - lo
        if not (self.p["min_range_atr"] * atr <= rng
                <= self.p["max_range_atr"] * atr):
            self._done = True                          # dead or hyper open
            return None
        buf = self.p["buffer_atr"] * atr
        mid = (hi + lo) / 2
        rr = self.p["target_rr"]
        if a["close"][i] > hi + buf:
            self._done = True                          # one-and-done
            stop = mid if self.p["stop_mode"] == "mid" else lo
            risk = a["close"][i] - stop
            return Entry("buy", "market", None, stop=stop,
                         target=a["close"][i] + rr * risk, tag="or_long")
        if a["close"][i] < lo - buf:
            self._done = True
            stop = mid if self.p["stop_mode"] == "mid" else hi
            risk = stop - a["close"][i]
            return Entry("sell", "market", None, stop=stop,
                         target=a["close"][i] - rr * risk, tag="or_short")
        return None


# ---------------------------------------------------------------- priority 1

class VwapRsiPullback(CardStrategy):
    name = "vwap_rsi_pullback"
    timeframe_min = 1
    notes = ("stop=trigger-bar extreme -2 ticks ('under VWAP'); target=1σ "
             "band at entry; RSI-exit via manage; 30min VWAP warmup")

    def prepare(self, df):
        v = ind.session_vwap(df)
        self._cols(df, vwap=v["vwap"], vwap_sd=v["vwap_sd"],
                   rsi=ind.rsi(df["close"], self.p["rsi_period"]))
        self.armed_long = self.armed_short = 0
        return df

    def on_bar(self, df, i):
        a = self.a
        if a["minutes_since_open"][i] < 30 or np.isnan(a["vwap"][i]):
            return None
        ttl = self.p["rsi_arm_ttl_bars"]
        if a["rsi"][i] < self.p["rsi_arm_below"]:
            self.armed_long = ttl
        if a["rsi"][i] > 100 - self.p["rsi_arm_below"]:
            self.armed_short = ttl
        self.armed_long = max(0, self.armed_long - 1)
        self.armed_short = max(0, self.armed_short - 1)
        vwap, sd = a["vwap"][i], a["vwap_sd"][i]
        if (self.armed_long and a["close"][i] > vwap
                and a["low"][i] <= vwap):          # touched, closed back above
            return Entry("buy", "market", None,
                         stop=a["low"][i] - 2 * self.tick,
                         target=vwap + sd, tag="vwap_hold_long")
        if (self.armed_short and a["close"][i] < vwap
                and a["high"][i] >= vwap):
            return Entry("sell", "market", None,
                         stop=a["high"][i] + 2 * self.tick,
                         target=vwap - sd, tag="vwap_hold_short")
        return None

    def manage(self, df, i, pos):
        r = self.a["rsi"][i]
        if pos.side == "buy" and r > self.p["rsi_exit_above"]:
            return "exit"
        if pos.side == "sell" and r < 100 - self.p["rsi_exit_above"]:
            return "exit"
        return None


class BbSqueezeBreakout(CardStrategy):
    name = "bb_squeeze_breakout"
    timeframe_min = 30
    notes = ("'BBW breaks flat base' = BBW pctile was <20 on prior bar and "
             "BBW expanding; SMA20 trail via manage")

    def prepare(self, df):
        bb = ind.bollinger(df["close"], self.p["bb_period"],
                           self.p["bb_stdev"])
        self._cols(df, bb_mid=bb["bb_mid"], bb_up=bb["bb_up"],
                   bb_dn=bb["bb_dn"],
                   bbw_pct=ind.rolling_percentile(
                       bb["bb_width"], self.p["bbw_lookback_bars"]),
                   bbw=bb["bb_width"])
        return df

    def on_bar(self, df, i):
        a = self.a
        if i < 1 or np.isnan(a["bbw_pct"][i - 1]):
            return None
        squeezed = a["bbw_pct"][i - 1] < self.p["bbw_squeeze_percentile"]
        expanding = a["bbw"][i] > a["bbw"][i - 1]
        if not (squeezed and expanding):
            return None
        if a["close"][i] > a["bb_up"][i]:
            return Entry("buy", "market", None, stop=a["bb_mid"][i])
        if a["close"][i] < a["bb_dn"][i]:
            return Entry("sell", "market", None, stop=a["bb_mid"][i])
        return None

    def manage(self, df, i, pos):
        mid, close = self.a["bb_mid"][i], self.a["close"][i]
        if pos.side == "buy" and close < mid:
            return "exit"
        if pos.side == "sell" and close > mid:
            return "exit"
        return mid


class CprDayRouter(CardStrategy):
    name = "cpr_day_router"
    timeframe_min = 5
    notes = ("narrow<=30th pctile of 60 sessions → TC/BC breakout to R1/S1; "
             "wide>=70th → band-hold reaction; else stands down")

    def prepare(self, df):
        piv = ind.daily_pivots(df)
        widths = piv.groupby(df["session_date"])["cpr_width"].first()
        pct = widths.rolling(60, min_periods=20).rank(pct=True) * 100
        self._cols(df, TC=piv["TC"], BC=piv["BC"], R1=piv["R1"],
                   S1=piv["S1"],
                   width_pct=pct.reindex(df["session_date"]).set_axis(df.index),
                   atr=ind.atr(df))
        return df

    def on_bar(self, df, i):
        a = self.a
        wp = a["width_pct"][i]
        if np.isnan(wp) or np.isnan(a["TC"][i]):
            return None
        buf = 0.1 * a["atr"][i]
        if wp <= 30:                                   # expansion day
            if a["close"][i] > a["TC"][i] + buf:
                return Entry("buy", "market", None, stop=a["BC"][i],
                             target=a["R1"][i], tag="narrow_break")
            if a["close"][i] < a["BC"][i] - buf:
                return Entry("sell", "market", None, stop=a["TC"][i],
                             target=a["S1"][i], tag="narrow_break")
        elif wp >= 70:                                 # rotational day
            if a["low"][i] <= a["TC"][i] and a["close"][i] > a["TC"][i]:
                return Entry("buy", "market", None,
                             stop=a["BC"][i] - buf,
                             target=a["R1"][i], tag="wide_hold")
            if a["high"][i] >= a["BC"][i] and a["close"][i] < a["BC"][i]:
                return Entry("sell", "market", None,
                             stop=a["TC"][i] + buf,
                             target=a["S1"][i], tag="wide_hold")
        return None


class SupertrendRsi(CardStrategy):
    name = "supertrend_rsi"
    timeframe_min = 30

    def prepare(self, df):
        st = ind.supertrend(df, self.p["supertrend"]["atr_period"],
                            self.p["supertrend"]["multiplier"])
        self._cols(df, st_line=st["st_line"], st_dir=st["st_dir"],
                   rsi=ind.rsi(df["close"], self.p["rsi_period"]))
        return df

    def on_bar(self, df, i):
        a = self.a
        if i < 1:
            return None
        flipped_up = a["st_dir"][i] > 0 > a["st_dir"][i - 1]
        flipped_dn = a["st_dir"][i] < 0 < a["st_dir"][i - 1]
        if flipped_up and a["rsi"][i] > self.p["rsi_confirm_long"]:
            return Entry("buy", "market", None, stop=a["st_line"][i])
        if flipped_dn and a["rsi"][i] < self.p["rsi_confirm_short"]:
            return Entry("sell", "market", None, stop=a["st_line"][i])
        return None

    def manage(self, df, i, pos):
        a = self.a
        if (pos.side == "buy" and a["st_dir"][i] < 0) or \
                (pos.side == "sell" and a["st_dir"][i] > 0):
            return "exit"
        return a["st_line"][i]


class EmaSnapbackScalp(CardStrategy):
    name = "ema_snapback_scalp"
    timeframe_min = 5
    notes = ("cancel-replace approximated by 3-bar entry TTL; EMA target "
             "frozen at signal (conservative — EMA converges toward price)")

    def prepare(self, df):
        self._cols(df, ema=ind.ema(df["close"], self.p["ema_period"]),
                   atr=ind.atr(df),
                   lo3=df["low"].rolling(3).min(),
                   hi3=df["high"].rolling(3).max())
        return df

    def on_bar(self, df, i):
        a = self.a
        det = self.p["detachment_min_atr"] * a["atr"][i]
        if np.isnan(det):
            return None
        if a["high"][i] < a["ema"][i] - det:           # fully below EMA
            return Entry("buy", "stop", a["high"][i] + self.tick,
                         stop=a["lo3"][i], target=a["ema"][i],
                         time_stop_bars=self.p["time_stop_bars"], ttl_bars=3)
        if a["low"][i] > a["ema"][i] + det:
            return Entry("sell", "stop", a["low"][i] - self.tick,
                         stop=a["hi3"][i], target=a["ema"][i],
                         time_stop_bars=self.p["time_stop_bars"], ttl_bars=3)
        return None


class EmaSrBreak(CardStrategy):
    name = "ema_sr_break"
    timeframe_min = 5
    notes = ("levels = prior-session H/L; stop = swing_lookback-bar swing; "
             "target = target_rr × risk; exit alt close-back-through slow EMA")
    # B1-grid tunables with the tournament-baseline defaults
    DEFAULTS = {"min_sep_atr": 0.25, "target_rr": 2.0, "swing_lookback": 5}

    def prepare(self, df):
        sw = int(self.p.get("swing_lookback", self.DEFAULTS["swing_lookback"]))
        self.min_sep_atr = float(self.p.get("min_sep_atr",
                                            self.DEFAULTS["min_sep_atr"]))
        self.target_rr = float(self.p.get("target_rr",
                                          self.DEFAULTS["target_rr"]))
        daily = df.groupby("session_date").agg(H=("high", "max"),
                                               L=("low", "min")).shift(1)
        lv = daily.reindex(df["session_date"]).set_index(df.index)
        self._cols(df, ema_f=ind.ema(df["close"], self.p["ema_fast"]),
                   ema_s=ind.ema(df["close"], self.p["ema_slow"]),
                   atr=ind.atr(df), ph=lv["H"], pl=lv["L"],
                   lo5=df["low"].rolling(sw).min(),
                   hi5=df["high"].rolling(sw).max())
        self.done_level = None
        return df

    def on_bar(self, df, i):
        a = self.a
        sep = a["ema_f"][i] - a["ema_s"][i]
        min_sep = self.min_sep_atr * a["atr"][i]
        if np.isnan(a["ph"][i]) or np.isnan(min_sep):
            return None
        if sep > min_sep and a["close"][i] > a["ph"][i] \
                and self.done_level != ("up", a["ph"][i]):
            self.done_level = ("up", a["ph"][i])       # one break per level
            stop = a["lo5"][i]
            risk = a["close"][i] - stop
            return Entry("buy", "market", None, stop=stop,
                         target=a["close"][i] + self.target_rr * risk)
        if sep < -min_sep and a["close"][i] < a["pl"][i] \
                and self.done_level != ("dn", a["pl"][i]):
            self.done_level = ("dn", a["pl"][i])
            stop = a["hi5"][i]
            risk = stop - a["close"][i]
            return Entry("sell", "market", None, stop=stop,
                         target=a["close"][i] - self.target_rr * risk)
        return None

    def manage(self, df, i, pos):
        a = self.a
        if pos.side == "buy" and a["close"][i] < a["ema_s"][i]:
            return "exit"
        if pos.side == "sell" and a["close"][i] > a["ema_s"][i]:
            return "exit"
        return None


# ---------------------------------------------------------------- priority 2

class TwoLeggedPullback(CardStrategy):
    name = "two_legged_pullback"
    timeframe_min = 15
    notes = ("legs = two down-swings (bar dips) after a new swing high, "
             "second undercutting first, above the major higher low; "
             "T2-only at 4R (1 contract), breakeven after 2R")

    def prepare(self, df):
        sw = ind.swing_pivots(df)
        self._cols(df, swing_hi=sw["swing_hi"], swing_lo=sw["swing_lo"],
                   swing_hi_prev=sw["swing_hi_prev"],
                   swing_lo_prev=sw["swing_lo_prev"])
        return df

    def _legs(self, a, i, direction):
        # last 12 bars: two distinct adverse dips, second beyond the first
        lo, hi = a["low"], a["high"]
        dips = []
        for k in range(max(1, i - 12), i + 1):
            if direction == "long" and lo[k] < lo[k - 1]:
                dips.append(lo[k])
            if direction == "short" and hi[k] > hi[k - 1]:
                dips.append(hi[k])
        if len(dips) < 2:
            return False
        return dips[-1] < dips[0] if direction == "long" \
            else dips[-1] > dips[0]

    def on_bar(self, df, i):
        a = self.a
        if np.isnan(a["swing_lo_prev"][i]):
            return None
        up = a["swing_hi"][i] > a["swing_hi_prev"][i] \
            and a["swing_lo"][i] > a["swing_lo_prev"][i]
        dn = a["swing_hi"][i] < a["swing_hi_prev"][i] \
            and a["swing_lo"][i] < a["swing_lo_prev"][i]
        bullish = a["close"][i] > a["open"][i]
        if up and bullish and a["low"][i] > a["swing_lo"][i] \
                and self._legs(a, i, "long"):
            risk = a["high"][i] + self.tick - a["low"][i]
            return Entry("buy", "stop", a["high"][i] + self.tick,
                         stop=a["low"][i],
                         target=a["high"][i] + self.tick
                         + self.p["targets"]["t2_rr"] * risk, ttl_bars=6)
        if dn and not bullish and a["high"][i] < a["swing_hi"][i] \
                and self._legs(a, i, "short"):
            risk = a["high"][i] - (a["low"][i] - self.tick)
            return Entry("sell", "stop", a["low"][i] - self.tick,
                         stop=a["high"][i],
                         target=a["low"][i] - self.tick
                         - self.p["targets"]["t2_rr"] * risk, ttl_bars=6)
        return None

    def manage(self, df, i, pos):
        if not self.p.get("breakeven_after_t1", False):
            return None
        risk = abs(pos.entry_price - pos.stop)
        close = self.a["close"][i]
        t1 = self.p["targets"]["t1_rr"]
        if pos.side == "buy" and close >= pos.entry_price + t1 * risk:
            return pos.entry_price
        if pos.side == "sell" and close <= pos.entry_price - t1 * risk:
            return pos.entry_price
        return None


class VolumeBreakout(CardStrategy):
    name = "volume_breakout"
    timeframe_min = 15
    notes = ("consolidation window = 8 bars; RVOL baseline = same "
             "minute-of-day 20-session mean")

    def prepare(self, df):
        self._cols(df, atr=ind.atr(df),
                   rvol=ind.rvol_baseline(df),
                   hi8=df["high"].rolling(8).max().shift(1),
                   lo8=df["low"].rolling(8).min().shift(1),
                   vol8=df["volume"].rolling(8).mean().shift(1))
        return df

    def on_bar(self, df, i):
        a = self.a
        rng = a["hi8"][i] - a["lo8"][i]
        base = a["rvol"][i]
        if np.isnan(rng) or np.isnan(base) or base <= 0:
            return None
        tight = rng <= self.p["consolidation_max_range_atr"] * a["atr"][i]
        quiet = a["vol8"][i] < self.p["low_volume_ratio"] * base
        body = abs(a["close"][i] - a["open"][i])
        strong = body >= self.p["breakout_body_atr"] * a["atr"][i] \
            and a["volume"][i] >= self.p["breakout_volume_ratio"] * base
        if not (tight and quiet and strong):
            return None
        if a["close"][i] > a["hi8"][i]:
            return Entry("buy", "market", None, stop=a["lo8"][i],
                         target=a["close"][i] + rng)
        if a["close"][i] < a["lo8"][i]:
            return Entry("sell", "market", None, stop=a["hi8"][i],
                         target=a["close"][i] - rng)
        return None


class MicroFlagScalp(CardStrategy):
    name = "micro_flag_scalp"
    timeframe_min = 1
    notes = ("cluster = 4 bars (middle of card's 3-6); target 1.5R; "
             "cancel-if-wrong-close approximated by 3-bar TTL")

    def prepare(self, df):
        v = ind.session_vwap(df)
        self._cols(df, atr=ind.atr(df), vwap=v["vwap"],
                   ema9=ind.ema(df["close"], 9),
                   ema21=ind.ema(df["close"], 21))
        return df

    def on_bar(self, df, i):
        a = self.a
        if a["minutes_since_open"][i] > \
                self.p["session_window_hours_after_open"] * 60 or i < 4:
            return None
        k = 4
        ranges = a["high"][i - k + 1:i + 1] - a["low"][i - k + 1:i + 1]
        if np.isnan(a["atr"][i]) or \
                not (ranges <= self.p["candle_max_atr"] * a["atr"][i]).all():
            return None
        c_hi = a["high"][i - k + 1:i + 1].max()
        c_lo = a["low"][i - k + 1:i + 1].min()
        long_ok = a["ema9"][i] > a["ema21"][i] or a["close"][i] > a["vwap"][i]
        short_ok = a["ema9"][i] < a["ema21"][i] or a["close"][i] < a["vwap"][i]
        risk = c_hi + self.tick - c_lo
        if long_ok:
            return Entry("buy", "stop", c_hi + self.tick, stop=c_lo,
                         target=c_hi + self.tick + 1.5 * risk, ttl_bars=3)
        if short_ok:
            return Entry("sell", "stop", c_lo - self.tick, stop=c_hi,
                         target=c_lo - self.tick - 1.5 * risk, ttl_bars=3)
        return None


class VwapBandFade(CardStrategy):
    name = "vwap_band_fade"
    timeframe_min = 5
    notes = ("flat-VWAP gate = |ΔVWAP over 10 bars| < 0.1 ATR; "
             "t1 target = VWAP (single contract)")

    def prepare(self, df):
        v = ind.session_vwap(df)
        self._cols(df, vwap=v["vwap"], sd=v["vwap_sd"], atr=ind.atr(df))
        return df

    def on_bar(self, df, i):
        a = self.a
        if a["minutes_since_open"][i] < 30 or i < 10 or np.isnan(a["sd"][i]):
            return None
        if abs(a["vwap"][i] - a["vwap"][i - 10]) >= 0.1 * a["atr"][i]:
            return None                               # not a rotational day
        k = self.p["entry_band_sigma"]
        up = a["vwap"][i] + k * a["sd"][i]
        dn = a["vwap"][i] - k * a["sd"][i]
        if a["high"][i] >= up and a["close"][i] < up:
            return Entry("sell", "market", None,
                         stop=a["high"][i] + 2 * self.tick,
                         target=a["vwap"][i])
        if a["low"][i] <= dn and a["close"][i] > dn:
            return Entry("buy", "market", None,
                         stop=a["low"][i] - 2 * self.tick,
                         target=a["vwap"][i])
        return None


class DonchianPullback(CardStrategy):
    name = "donchian_pullback"
    timeframe_min = 15
    notes = "trend = channel high advanced within last 10 bars; 5-bar swing stop"

    def prepare(self, df):
        dc = ind.donchian(df, self.p["period"])
        self._cols(df, dc_hi=dc["dc_hi"], dc_lo=dc["dc_lo"],
                   dc_mid=dc["dc_mid"],
                   lo5=df["low"].rolling(5).min(),
                   hi5=df["high"].rolling(5).max())
        return df

    def on_bar(self, df, i):
        a = self.a
        if i < 10 or np.isnan(a["dc_mid"][i]):
            return None
        width = a["dc_hi"][i] - a["dc_lo"][i]
        tol = self.p["pullback_tolerance_channel_width"] * width
        up_trend = a["dc_hi"][i] > a["dc_hi"][i - 10]
        dn_trend = a["dc_lo"][i] < a["dc_lo"][i - 10]
        if up_trend and abs(a["low"][i] - a["dc_mid"][i]) <= tol \
                and a["close"][i] > a["dc_mid"][i]:
            return Entry("buy", "stop", a["high"][i] + self.tick,
                         stop=a["lo5"][i], ttl_bars=4)
        if dn_trend and abs(a["high"][i] - a["dc_mid"][i]) <= tol \
                and a["close"][i] < a["dc_mid"][i]:
            return Entry("sell", "stop", a["low"][i] - self.tick,
                         stop=a["hi5"][i], ttl_bars=4)
        return None

    def manage(self, df, i, pos):
        a = self.a
        if pos.side == "buy" and a["close"][i] < a["dc_mid"][i]:
            return "exit"
        if pos.side == "sell" and a["close"][i] > a["dc_mid"][i]:
            return "exit"
        return None


class FractalTrend(CardStrategy):
    name = "fractal_trend"
    timeframe_min = 15

    def prepare(self, df):
        fr = ind.fractals(df)
        self._cols(df, f_up=fr["fractal_up"], f_dn=fr["fractal_dn"],
                   sma=ind.sma(df["close"], self.p["sma_filter"]),
                   atr=ind.atr(df))
        return df

    def on_bar(self, df, i):
        a = self.a
        buf = self.p["sma_buffer_atr"] * a["atr"][i]
        if np.isnan(a["sma"][i]) or np.isnan(a["f_up"][i]) \
                or np.isnan(a["f_dn"][i]):
            return None
        if a["close"][i] > a["sma"][i] + buf and a["f_up"][i] > a["close"][i]:
            return Entry("buy", "stop", a["f_up"][i] + self.tick,
                         stop=a["f_dn"][i], ttl_bars=10)
        if a["close"][i] < a["sma"][i] - buf and a["f_dn"][i] < a["close"][i]:
            return Entry("sell", "stop", a["f_dn"][i] - self.tick,
                         stop=a["f_up"][i], ttl_bars=10)
        return None

    def manage(self, df, i, pos):
        a = self.a
        return a["f_dn"][i] if pos.side == "buy" else a["f_up"][i]


class ZoneSweep(CardStrategy):
    name = "zone_sweep"
    timeframe_min = 15
    notes = ("liquidity level = prior-session extreme (volume zones "
             "deferred to the levels service); target = prior-day pivot P; "
             "min RR 1.5 enforced")

    def prepare(self, df):
        piv = ind.daily_pivots(df)
        daily = df.groupby("session_date").agg(H=("high", "max"),
                                               L=("low", "min")).shift(1)
        lv = daily.reindex(df["session_date"]).set_index(df.index)
        self._cols(df, P=piv["P"], ph=lv["H"], pl=lv["L"])
        return df

    def on_bar(self, df, i):
        a = self.a
        if np.isnan(a["pl"][i]):
            return None
        pen = self.p["sweep_max_penetration_ticks"] * self.tick
        buf = self.p["stop_buffer_ticks"] * self.tick
        if a["pl"][i] - pen <= a["low"][i] < a["pl"][i] \
                and a["close"][i] > a["pl"][i]:        # swept the low, reclaimed
            stop = a["low"][i] - buf
            rr = (a["P"][i] - a["close"][i]) / max(a["close"][i] - stop,
                                                   TICK_EPS)
            if rr >= self.p["min_rr"]:
                return Entry("buy", "market", None, stop=stop,
                             target=a["P"][i], tag="sweep_low")
        if a["ph"][i] < a["high"][i] <= a["ph"][i] + pen \
                and a["close"][i] < a["ph"][i]:
            stop = a["high"][i] + buf
            rr = (a["close"][i] - a["P"][i]) / max(stop - a["close"][i],
                                                   TICK_EPS)
            if rr >= self.p["min_rr"]:
                return Entry("sell", "market", None, stop=stop,
                             target=a["P"][i], tag="sweep_high")
        return None


class StructureBreak(CardStrategy):
    name = "structure_break"
    timeframe_min = 15

    def prepare(self, df):
        sw = ind.swing_pivots(df)
        self._cols(df, swing_hi=sw["swing_hi"], swing_lo=sw["swing_lo"],
                   swing_hi_prev=sw["swing_hi_prev"],
                   swing_lo_prev=sw["swing_lo_prev"], atr=ind.atr(df))
        return df

    def on_bar(self, df, i):
        a = self.a
        if np.isnan(a["swing_lo_prev"][i]):
            return None
        buf = self.p["buffer_atr"] * a["atr"][i]
        up = a["swing_hi"][i] > a["swing_hi_prev"][i] \
            and a["swing_lo"][i] > a["swing_lo_prev"][i]
        dn = a["swing_hi"][i] < a["swing_hi_prev"][i] \
            and a["swing_lo"][i] < a["swing_lo_prev"][i]
        if up and a["close"][i] > a["swing_hi"][i] + buf:
            risk = a["close"][i] - a["swing_lo"][i]
            return Entry("buy", "market", None, stop=a["swing_lo"][i],
                         target=a["close"][i]
                         + self.p["targets"]["t1_rr"] * risk)
        if dn and a["close"][i] < a["swing_lo"][i] - buf:
            risk = a["swing_hi"][i] - a["close"][i]
            return Entry("sell", "market", None, stop=a["swing_hi"][i],
                         target=a["close"][i]
                         - self.p["targets"]["t1_rr"] * risk)
        return None


class PinbarZoneFade(CardStrategy):
    name = "pinbar_zone_fade"
    timeframe_min = 15
    notes = ("zone = prior-session extreme ± 0.5 ATR; range regime = EMA9/21 "
             "separation < 0.25 ATR")

    def prepare(self, df):
        daily = df.groupby("session_date").agg(H=("high", "max"),
                                               L=("low", "min")).shift(1)
        lv = daily.reindex(df["session_date"]).set_index(df.index)
        self._cols(df, ph=lv["H"], pl=lv["L"], atr=ind.atr(df),
                   ema9=ind.ema(df["close"], 9),
                   ema21=ind.ema(df["close"], 21))
        return df

    def on_bar(self, df, i):
        a = self.a
        if np.isnan(a["ph"][i]) or np.isnan(a["atr"][i]):
            return None
        if abs(a["ema9"][i] - a["ema21"][i]) >= 0.25 * a["atr"][i]:
            return None                                # trending — no fades
        body = abs(a["close"][i] - a["open"][i]) + TICK_EPS
        buf = self.p["stop_buffer_ticks"] * self.tick
        zone = 0.5 * a["atr"][i]
        up_wick = a["high"][i] - max(a["close"][i], a["open"][i])
        dn_wick = min(a["close"][i], a["open"][i]) - a["low"][i]
        rng = a["ph"][i] - a["pl"][i]
        if dn_wick / body >= self.p["wick_body_ratio"] \
                and abs(a["low"][i] - a["pl"][i]) <= zone \
                and a["close"][i] > a["pl"][i]:
            stop = a["low"][i] - buf
            if rng >= self.p["min_range_to_risk"] * (a["close"][i] - stop):
                return Entry("buy", "market", None, stop=stop,
                             target=a["ph"][i])
        if up_wick / body >= self.p["wick_body_ratio"] \
                and abs(a["high"][i] - a["ph"][i]) <= zone \
                and a["close"][i] < a["ph"][i]:
            stop = a["high"][i] + buf
            if rng >= self.p["min_range_to_risk"] * (stop - a["close"][i]):
                return Entry("sell", "market", None, stop=stop,
                             target=a["pl"][i])
        return None


class VcpBreakout(CardStrategy):
    name = "vcp_breakout"
    timeframe_min = 240
    notes = ("base = 20 bars split in halves: depth2 <= 0.7×depth1 and "
             "volume drying up; entry stop above the ceiling; measured-move "
             "target; long only per card")

    def prepare(self, df):
        self._cols(df, atr=ind.atr(df))
        return df

    def on_bar(self, df, i):
        a = self.a
        n = 20
        if i < n:
            return None
        hi = a["high"][i - n + 1:i + 1]
        lo = a["low"][i - n + 1:i + 1]
        vol = a["volume"][i - n + 1:i + 1]
        ceiling = hi.max()
        half = n // 2
        depth1 = ceiling - lo[:half].min()
        depth2 = ceiling - lo[half:].min()
        dry = vol[half:].mean() < 0.85 * vol[:half].mean()
        if depth1 <= 0 or depth2 > self.p["contraction_ratio"] * depth1:
            return None
        if self.p.get("volume_dry_up_filter") and not dry:
            return None
        return Entry("buy", "stop", ceiling + self.tick,
                     stop=lo[half:].min(),
                     target=ceiling + depth1, ttl_bars=6)


# ---------------------------------------------------------------- priority 3

class RsiReversion(CardStrategy):
    name = "rsi_reversion"
    timeframe_min = 15
    notes = ("base variant (confirmation_filter none); range regime = "
             "EMA9/21 separation < 0.25 ATR; opposite-band rule exit")

    def prepare(self, df):
        self._cols(df, rsi=ind.rsi(df["close"], self.p["rsi_period"]),
                   atr=ind.atr(df),
                   ema9=ind.ema(df["close"], 9),
                   ema21=ind.ema(df["close"], 21),
                   lo5=df["low"].rolling(5).min(),
                   hi5=df["high"].rolling(5).max())
        return df

    def on_bar(self, df, i):
        a = self.a
        if i < 1 or abs(a["ema9"][i] - a["ema21"][i]) >= 0.25 * a["atr"][i]:
            return None
        if a["rsi"][i - 1] < 30 <= a["rsi"][i]:        # turning back out
            return Entry("buy", "market", None, stop=a["lo5"][i],
                         time_stop_bars=self.p["time_stop_bars"])
        if a["rsi"][i - 1] > 70 >= a["rsi"][i]:
            return Entry("sell", "market", None, stop=a["hi5"][i],
                         time_stop_bars=self.p["time_stop_bars"])
        return None

    def manage(self, df, i, pos):
        r = self.a["rsi"][i]
        if pos.side == "buy" and r >= 70:
            return "exit"
        if pos.side == "sell" and r <= 30:
            return "exit"
        return None


class SarRsiScalp(CardStrategy):
    name = "sar_rsi_scalp"
    timeframe_min = 3

    def prepare(self, df):
        ps = ind.psar(df)
        self._cols(df, sar=ps["sar"], sar_dir=ps["sar_dir"],
                   rsi=ind.rsi(df["close"], 14), atr=ind.atr(df))
        return df

    def on_bar(self, df, i):
        a = self.a
        if i < 1 or np.isnan(a["sar"][i]) or np.isnan(a["atr"][i]):
            return None
        floor = self.p["min_stop_atr"] * a["atr"][i]
        if a["sar_dir"][i] > 0 > a["sar_dir"][i - 1] and a["rsi"][i] > 50:
            stop = min(a["sar"][i], a["close"][i] - floor)
            return Entry("buy", "market", None, stop=stop)
        if a["sar_dir"][i] < 0 < a["sar_dir"][i - 1] and a["rsi"][i] < 50:
            stop = max(a["sar"][i], a["close"][i] + floor)
            return Entry("sell", "market", None, stop=stop)
        return None

    def manage(self, df, i, pos):
        a = self.a
        if (pos.side == "buy" and a["sar_dir"][i] < 0) or \
                (pos.side == "sell" and a["sar_dir"][i] > 0):
            return "exit"
        return a["sar"][i]


class TrendlineRetest(CardStrategy):
    name = "trendline_retest"
    timeframe_min = 15
    notes = "regression channel(50); retest window 12 bars; projected target"

    def prepare(self, df):
        rc = ind.regression_channel(df["close"], self.p["regression_bars"])
        self._cols(df, reg_up=rc["reg_up"], reg_dn=rc["reg_dn"],
                   reg_mid=rc["reg_mid"], atr=ind.atr(df))
        self.pending = None            # ("up"|"dn", level, bars_left)
        return df

    def on_bar(self, df, i):
        a = self.a
        if np.isnan(a["reg_up"][i]) or np.isnan(a["atr"][i]):
            return None
        buf = 0.1 * a["atr"][i]
        tol = 0.25 * a["atr"][i]
        height = a["reg_up"][i] - a["reg_dn"][i]
        if self.pending:
            side, level, left = self.pending
            self.pending = (side, level, left - 1) if left > 1 else None
            if side == "up" and abs(a["low"][i] - level) <= tol \
                    and a["close"][i] > level:
                self.pending = None
                return Entry("buy", "market", None,
                             stop=a["low"][i] - 2 * self.tick,
                             target=level + height)
            if side == "dn" and abs(a["high"][i] - level) <= tol \
                    and a["close"][i] < level:
                self.pending = None
                return Entry("sell", "market", None,
                             stop=a["high"][i] + 2 * self.tick,
                             target=level - height)
        elif a["close"][i] > a["reg_up"][i] + buf:
            self.pending = ("up", a["reg_up"][i], 12)
        elif a["close"][i] < a["reg_dn"][i] - buf:
            self.pending = ("dn", a["reg_dn"][i], 12)
        return None


class BbFakeMove(CardStrategy):
    name = "bb_fake_move"
    timeframe_min = 15
    notes = ("uptrend = mid-band rising over 5 bars; reclaim = first bullish "
             "close after a band touch that never closed below; long only")

    def prepare(self, df):
        bb = ind.bollinger(df["close"])
        self._cols(df, bb_mid=bb["bb_mid"], bb_up=bb["bb_up"],
                   bb_dn=bb["bb_dn"], atr=ind.atr(df))
        self.touched = None            # low of the touch sequence
        return df

    def on_bar(self, df, i):
        a = self.a
        if i < 5 or np.isnan(a["bb_dn"][i]):
            return None
        rising = a["bb_mid"][i] > a["bb_mid"][i - 5]
        if not rising:
            self.touched = None
            return None
        near = a["low"][i] <= a["bb_dn"][i] + 0.25 * a["atr"][i]
        broke = a["close"][i] < a["bb_dn"][i]
        if broke:                                     # band did NOT hold
            self.touched = None
            return None
        if near:
            self.touched = (a["low"][i] if self.touched is None
                            else min(self.touched, a["low"][i]))
            return None
        if self.touched is not None and a["close"][i] > a["open"][i]:
            stop = self.touched - self.tick
            self.touched = None
            return Entry("buy", "stop", a["high"][i] + self.tick,
                         stop=stop, target=a["bb_up"][i], ttl_bars=4)
        return None


class PivotLevels(CardStrategy):
    name = "pivot_levels"
    timeframe_min = 5
    notes = ("retest mode; levels P/R1/S1, ladder target = next level out; "
             "retest tolerance 0.25 ATR")

    def prepare(self, df):
        piv = ind.daily_pivots(df)
        self._cols(df, P=piv["P"], R1=piv["R1"], R2=piv["R2"],
                   S1=piv["S1"], S2=piv["S2"], atr=ind.atr(df))
        self.pending = None            # (side, level, target, bars_left)
        return df

    def on_bar(self, df, i):
        a = self.a
        if np.isnan(a["P"][i]) or np.isnan(a["atr"][i]):
            return None
        tol = 0.25 * a["atr"][i]
        buf = 0.1 * a["atr"][i]
        if self.pending:
            side, level, target, left = self.pending
            self.pending = (side, level, target, left - 1) if left > 1 else None
            if side == "buy" and a["close"][i] < level - buf:
                self.pending = None                    # break failed
            elif side == "sell" and a["close"][i] > level + buf:
                self.pending = None
            elif side == "buy" and abs(a["low"][i] - level) <= tol \
                    and a["close"][i] > level:
                self.pending = None
                return Entry("buy", "market", None,
                             stop=a["low"][i] - 2 * self.tick, target=target)
            elif side == "sell" and abs(a["high"][i] - level) <= tol \
                    and a["close"][i] < level:
                self.pending = None
                return Entry("sell", "market", None,
                             stop=a["high"][i] + 2 * self.tick, target=target)
            return None
        window = self.p["retest_window_bars"]
        for level, target in ((a["P"][i], a["R1"][i]),
                              (a["R1"][i], a["R2"][i])):
            if a["close"][i] > level + buf and a["open"][i] <= level:
                self.pending = ("buy", level, target, window)
                return None
        for level, target in ((a["P"][i], a["S1"][i]),
                              (a["S1"][i], a["S2"][i])):
            if a["close"][i] < level - buf and a["open"][i] >= level:
                self.pending = ("sell", level, target, window)
                return None
        return None


ALL_STRATEGIES: dict[str, type[CardStrategy]] = {
    cls.name: cls for cls in (
        OpeningRange,
        VwapRsiPullback, BbSqueezeBreakout, CprDayRouter, SupertrendRsi,
        EmaSnapbackScalp, EmaSrBreak, TwoLeggedPullback, VolumeBreakout,
        MicroFlagScalp, VwapBandFade, DonchianPullback, FractalTrend,
        ZoneSweep, StructureBreak, PinbarZoneFade, VcpBreakout,
        RsiReversion, SarRsiScalp, TrendlineRetest, BbFakeMove, PivotLevels,
    )
}

# a gate, not a standalone strategy — judged by improvement added (its card)
GATES = ("sector_confirmation",)
