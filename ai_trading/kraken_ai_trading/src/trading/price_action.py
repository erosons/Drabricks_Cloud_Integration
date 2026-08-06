"""
Price action layer — trend filter + exhaustion/reversal detector.

Three components work together:

1. EMA Trend Filter
   Tracks fast and slow exponential moving averages on the mid-price.
   Trend = UP when fast EMA > slow EMA, DOWN when fast < slow.
   Gates trades: only take flow signals that agree with the trend.

2. Spike / Exhaustion Detector
   Detects V-bottoms and V-tops (capitulation reversals):
   - V-bottom: price drops > spike_threshold from slow EMA, then recovers
     > recovery_pct of that drop. Signals: exhaustion=BUY.
   - V-top: price rises > spike_threshold then rejects > recovery_pct.
     Signals: exhaustion=SELL.
   Exhaustion signal stays active for exhaustion_ttl ticks after detection,
   giving the strategy a window to enter the reversal.

3. Demand / Supply Zone Scorer (5-factor, max = 8.0)
   Every confirmed V-bottom (demand) or V-top (supply) is scored on:

   Factor          Weight   Best case
   ─────────────── ──────── ──────────────────────────────
   Strength          0-2    Move-out AND breakout of prior ref
   Time              0-1    1-3 basing ticks (sharp, not slow)
   Freshness         0-2    Zone never pierced since creation
   Trend (ITF)       0-2    EMA trend agrees with zone direction
   Curve loc (HTF)   0-1    Zone at the right end of range

   A zone must score ≥ min_zone_score (default 5/8) for its exhaustion
   signal to pass through to order entry.

4. Re-test Detector
   Levels saved in _level_memory. When price returns within
   retest_proximity, the exhaustion signal re-arms — but only if the
   zone still scores above threshold after freshness is re-evaluated.
"""

from collections import deque
from dataclasses import dataclass
from typing import Optional

from .signals import Signal
from ..utils.logger import get_logger


# ---------------------------------------------------------------------------
# Public data types
# ---------------------------------------------------------------------------

@dataclass
class ZoneScore:
    """5-factor demand/supply zone score (max 8.0)."""
    strength: float    # 0 / 1 / 2
    time: float        # 0 / 0.5 / 1
    freshness: float   # 0 / 1 / 2
    trend: float       # 0 / 1 / 2
    curve: float       # 0 / 0.5 / 1

    @property
    def total(self) -> float:
        return self.strength + self.time + self.freshness + self.trend + self.curve

    def __str__(self) -> str:
        return (
            f"total={self.total:.1f}/8  "
            f"str={self.strength} time={self.time} "
            f"fresh={self.freshness} trend={self.trend} curve={self.curve}"
        )


@dataclass
class PriceActionSignal:
    trend: Signal          # EMA direction: BUY (up) / SELL (down) / NEUTRAL
    exhaustion: Signal     # V-bottom=BUY, V-top=SELL, NEUTRAL=none
    at_extreme: bool       # price near N-tick high or low
    fast_ema: float
    slow_ema: float
    zone_score: float      # active zone score (0-8), 0 if no active zone
    reasoning: str


# ---------------------------------------------------------------------------
# Internal zone level entry
# ---------------------------------------------------------------------------

@dataclass
class _ZoneLevel:
    """A confirmed V-bottom or V-top with its scoring state."""
    level: float          # spike extreme (zone anchor price)
    direction: Signal     # BUY = demand zone, SELL = supply zone
    zone_ref: float       # slow EMA at spike start (used for zone height + pierce calc)
    confirm_strength: float   # strength score at confirmation (fixed)
    time_score: float         # time score at confirmation (fixed)
    best_pierce: float        # max fraction into zone price has reached (0-1)
    ticks_left: int


# ---------------------------------------------------------------------------
# Analyzer
# ---------------------------------------------------------------------------

class PriceActionAnalyzer:
    """
    Tick-level price action analyzer.

    Call on_price_tick() on every book update (mid-price).
    Call analyze() to get the current PriceActionSignal for gating order entries.
    """

    _IDLE = "idle"
    _SPIKE_DOWN = "spike_down"
    _SPIKE_UP = "spike_up"

    def __init__(
        self,
        fast_period: int = 20,
        slow_period: int = 60,
        spike_threshold: float = 0.003,
        recovery_pct: float = 0.5,
        extreme_window: int = 200,
        extreme_proximity: float = 0.002,
        exhaustion_ttl: int = 60,
        spike_timeout: int = 80,
        trend_min_diff: float = 0.0005,
        retest_proximity: float = 0.002,
        retest_memory_ticks: int = 400,
        retest_ttl: int = 40,
        # Zone scoring thresholds
        min_zone_score: float = 5.0,    # reject zones scoring below this (out of 8)
        basing_ticks_fast: int = 5,     # ≤ N ticks = "1-3 candles" (best time score)
        basing_ticks_slow: int = 15,    # ≤ N ticks = "4-6 candles" (good time score)
    ) -> None:
        self.fast_period = fast_period
        self.slow_period = slow_period
        self.spike_threshold = spike_threshold
        self.recovery_pct = recovery_pct
        self.extreme_proximity = extreme_proximity
        self.exhaustion_ttl = exhaustion_ttl
        self.spike_timeout = spike_timeout
        self.trend_min_diff = trend_min_diff
        self.retest_proximity = retest_proximity
        self.retest_memory_ticks = retest_memory_ticks
        self.retest_ttl = retest_ttl
        self.min_zone_score = min_zone_score
        self.basing_ticks_fast = basing_ticks_fast
        self.basing_ticks_slow = basing_ticks_slow

        # EMA state
        self._fast_ema: Optional[float] = None
        self._slow_ema: Optional[float] = None
        self._alpha_fast = 2.0 / (fast_period + 1)
        self._alpha_slow = 2.0 / (slow_period + 1)
        self._tick_count = 0

        # Spike detector state
        self._spike_state: str = self._IDLE
        self._spike_ref: float = 0.0
        self._spike_extreme: float = 0.0
        self._spike_ticks: int = 0

        # Exhaustion output
        self._exhaustion: Signal = Signal.NEUTRAL
        self._exhaustion_ttl_remaining: int = 0
        self._active_zone_score: float = 0.0   # score of the currently active zone

        # Level memory — list of _ZoneLevel entries
        self._level_memory: list[_ZoneLevel] = []

        # Extremes
        self._prices: deque = deque(maxlen=extreme_window)

        self.log = get_logger(__name__)

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def on_price_tick(self, mid: float) -> None:
        if mid <= 0:
            return
        self._tick_count += 1
        self._prices.append(mid)
        self._update_emas(mid)
        self._update_spike_detector(mid)
        self._update_level_memory(mid)

    def analyze(self) -> PriceActionSignal:
        fast = self._fast_ema or 0.0
        slow = self._slow_ema or 0.0
        current = self._prices[-1] if self._prices else 0.0

        # --- Trend from EMA ---
        if self._tick_count < self.slow_period or slow == 0:
            trend = Signal.NEUTRAL
        else:
            diff_pct = (fast - slow) / slow
            if diff_pct > self.trend_min_diff:
                trend = Signal.BUY
            elif diff_pct < -self.trend_min_diff:
                trend = Signal.SELL
            else:
                trend = Signal.NEUTRAL

        # --- Price extreme ---
        at_extreme = False
        if len(self._prices) >= 20 and current > 0:
            period_low = min(self._prices)
            period_high = max(self._prices)
            at_low = (current - period_low) / current <= self.extreme_proximity
            at_high = period_high > 0 and (period_high - current) / period_high <= self.extreme_proximity
            at_extreme = at_low or at_high

        reasoning = (
            f"fast={fast:.5f} slow={slow:.5f} trend={trend.value} "
            f"exhaustion={self._exhaustion.value}({self._exhaustion_ttl_remaining}tks) "
            f"zone_score={self._active_zone_score:.1f} "
            f"spike={self._spike_state} at_extreme={at_extreme}"
        )

        return PriceActionSignal(
            trend=trend,
            exhaustion=self._exhaustion,
            at_extreme=at_extreme,
            fast_ema=fast,
            slow_ema=slow,
            zone_score=self._active_zone_score,
            reasoning=reasoning,
        )

    # ------------------------------------------------------------------
    # Internal — EMA
    # ------------------------------------------------------------------

    def _update_emas(self, price: float) -> None:
        if self._fast_ema is None:
            self._fast_ema = price
            self._slow_ema = price
        else:
            self._fast_ema = self._alpha_fast * price + (1 - self._alpha_fast) * self._fast_ema
            self._slow_ema = self._alpha_slow * price + (1 - self._alpha_slow) * self._slow_ema

    # ------------------------------------------------------------------
    # Internal — Zone scoring helpers
    # ------------------------------------------------------------------

    def _score_strength(
        self,
        spike_extreme: float,
        spike_ref: float,
        confirm_price: float,
        direction: Signal,
    ) -> float:
        """
        2 = strong move-out AND breakout past spike_ref
        1 = only one of the two
        0 = neither
        """
        zone_height = abs(spike_ref - spike_extreme)
        if zone_height == 0 or spike_ref == 0:
            return 0.0

        # Strong move-out: spike was at least 2× the threshold
        is_strong = zone_height / spike_ref >= 2 * self.spike_threshold

        # Breakout: confirm price went past the reference level
        if direction == Signal.BUY:
            is_breakout = confirm_price >= spike_ref
        else:
            is_breakout = confirm_price <= spike_ref

        if is_strong and is_breakout:
            return 2.0
        if is_strong or is_breakout:
            return 1.0
        return 0.0

    def _score_time(self, spike_ticks: int) -> float:
        """
        1.0 = 1-3 basing ticks (sharp zone, best)
        0.5 = 4-6 basing ticks
        0.0 = >6 basing ticks (slow, weak)
        """
        if spike_ticks <= self.basing_ticks_fast:
            return 1.0
        if spike_ticks <= self.basing_ticks_slow:
            return 0.5
        return 0.0

    def _score_freshness(self, best_pierce: float) -> float:
        """
        2.0 = not pierced at all
        1.0 = pierced ≤50% of zone height
        0.0 = pierced >50%
        """
        if best_pierce == 0.0:
            return 2.0
        if best_pierce <= 0.5:
            return 1.0
        return 0.0

    def _score_trend(self, direction: Signal) -> float:
        """
        Demand (BUY): uptrend=2, sideways=1, downtrend=0
        Supply (SELL): downtrend=2, sideways=1, uptrend=0
        """
        if self._slow_ema is None or self._tick_count < self.slow_period:
            return 1.0  # insufficient data — treat as sideways
        slow = self._slow_ema
        fast = self._fast_ema or slow
        diff_pct = (fast - slow) / slow if slow else 0.0
        if diff_pct > self.trend_min_diff:
            ema_trend = Signal.BUY
        elif diff_pct < -self.trend_min_diff:
            ema_trend = Signal.SELL
        else:
            ema_trend = Signal.NEUTRAL

        if direction == Signal.BUY:
            return 2.0 if ema_trend == Signal.BUY else (1.0 if ema_trend == Signal.NEUTRAL else 0.0)
        else:
            return 2.0 if ema_trend == Signal.SELL else (1.0 if ema_trend == Signal.NEUTRAL else 0.0)

    def _score_curve(self, zone_extreme: float, direction: Signal) -> float:
        """
        Position of zone within the rolling extreme_window range (HTF proxy).
        Demand at LOW of range = best (1.0). Supply at HIGH of range = best (1.0).
        Middle of range = 0.5. Wrong end = 0.0.
        """
        if len(self._prices) < 20:
            return 0.5  # not enough history

        lo = min(self._prices)
        hi = max(self._prices)
        span = hi - lo
        if span <= 0:
            return 0.5

        # Where does the zone extreme sit in [lo, hi]?
        position = (zone_extreme - lo) / span  # 0 = at low, 1 = at high

        if direction == Signal.BUY:   # demand zone: want to be at the low
            if position <= 0.333:
                return 1.0
            if position <= 0.667:
                return 0.5
            return 0.0
        else:                         # supply zone: want to be at the high
            if position >= 0.667:
                return 1.0
            if position >= 0.333:
                return 0.5
            return 0.0

    def _compute_zone_score(self, zone: _ZoneLevel) -> ZoneScore:
        """Full 5-factor score for a zone, using current trend/curve state."""
        freshness = self._score_freshness(zone.best_pierce)
        trend = self._score_trend(zone.direction)
        curve = self._score_curve(zone.level, zone.direction)
        return ZoneScore(
            strength=zone.confirm_strength,
            time=zone.time_score,
            freshness=freshness,
            trend=trend,
            curve=curve,
        )

    def _pierce_fraction(self, price: float, zone: _ZoneLevel) -> float:
        """How deep has price penetrated into the zone (0 = not at all, 1 = fully through)."""
        zone_height = abs(zone.zone_ref - zone.level)
        if zone_height == 0:
            return 0.0
        if zone.direction == Signal.BUY:
            # DZ: zone_ref is above level (spike_ref > spike_extreme)
            # Price approaches from above. Pierce = how far below zone_ref price is.
            return max(0.0, min(1.0, (zone.zone_ref - price) / zone_height))
        else:
            # SZ: zone_ref is below level (spike_ref < spike_extreme)
            # Price approaches from below. Pierce = how far above zone_ref price is.
            return max(0.0, min(1.0, (price - zone.zone_ref) / zone_height))

    # ------------------------------------------------------------------
    # Internal — Spike / exhaustion detector
    # ------------------------------------------------------------------

    def _update_spike_detector(self, price: float) -> None:
        if self._exhaustion_ttl_remaining > 0:
            self._exhaustion_ttl_remaining -= 1
            if self._exhaustion_ttl_remaining == 0:
                self._exhaustion = Signal.NEUTRAL
                self._active_zone_score = 0.0

        if self._slow_ema is None or self._tick_count < self.slow_period:
            return

        ref = self._slow_ema

        if self._spike_state == self._IDLE:
            pct = (price - ref) / ref
            if pct <= -self.spike_threshold:
                self._spike_state = self._SPIKE_DOWN
                self._spike_ref = ref
                self._spike_extreme = price
                self._spike_ticks = 0
            elif pct >= self.spike_threshold:
                self._spike_state = self._SPIKE_UP
                self._spike_ref = ref
                self._spike_extreme = price
                self._spike_ticks = 0

        elif self._spike_state == self._SPIKE_DOWN:
            self._spike_ticks += 1
            if price < self._spike_extreme:
                self._spike_extreme = price

            total_drop = self._spike_ref - self._spike_extreme
            if total_drop > 0:
                recovery = (price - self._spike_extreme) / total_drop
                if recovery >= self.recovery_pct:
                    self._confirm_zone(
                        spike_extreme=self._spike_extreme,
                        spike_ref=self._spike_ref,
                        confirm_price=price,
                        spike_ticks=self._spike_ticks,
                        direction=Signal.BUY,
                        drop_pct=(total_drop / self._spike_ref) * 100,
                        recovery_pct_actual=recovery * 100,
                    )
                    return

            if self._spike_ticks >= self.spike_timeout:
                self.log.debug("Spike DOWN timed out (%.2f%% drop), resetting",
                               (self._spike_ref - self._spike_extreme) / self._spike_ref * 100)
                self._spike_state = self._IDLE

        elif self._spike_state == self._SPIKE_UP:
            self._spike_ticks += 1
            if price > self._spike_extreme:
                self._spike_extreme = price

            total_rise = self._spike_extreme - self._spike_ref
            if total_rise > 0:
                rejection = (self._spike_extreme - price) / total_rise
                if rejection >= self.recovery_pct:
                    self._confirm_zone(
                        spike_extreme=self._spike_extreme,
                        spike_ref=self._spike_ref,
                        confirm_price=price,
                        spike_ticks=self._spike_ticks,
                        direction=Signal.SELL,
                        drop_pct=(total_rise / self._spike_ref) * 100,
                        recovery_pct_actual=rejection * 100,
                    )
                    return

            if self._spike_ticks >= self.spike_timeout:
                self.log.debug("Spike UP timed out (%.2f%% rise), resetting",
                               (self._spike_extreme - self._spike_ref) / self._spike_ref * 100)
                self._spike_state = self._IDLE

    def _confirm_zone(
        self,
        spike_extreme: float,
        spike_ref: float,
        confirm_price: float,
        spike_ticks: int,
        direction: Signal,
        drop_pct: float,
        recovery_pct_actual: float,
    ) -> None:
        """Score a freshly confirmed V-bottom/V-top and decide whether to arm exhaustion."""
        self._spike_state = self._IDLE

        # Score the 5 drivers
        s_strength = self._score_strength(spike_extreme, spike_ref, confirm_price, direction)
        s_time = self._score_time(spike_ticks)
        s_freshness = 2.0  # always fresh at confirmation
        s_trend = self._score_trend(direction)
        s_curve = self._score_curve(spike_extreme, direction)
        score = ZoneScore(
            strength=s_strength, time=s_time, freshness=s_freshness,
            trend=s_trend, curve=s_curve,
        )

        kind = "V-bottom (DZ)" if direction == Signal.BUY else "V-top (SZ)"
        self.log.info(
            "%s: ref=%.5f extreme=%.5f confirm=%.5f  "
            "move=%.2f%% recovery=%.0f%%  ticks=%d  |  %s",
            kind, spike_ref, spike_extreme, confirm_price,
            drop_pct, recovery_pct_actual, spike_ticks, score,
        )

        # Save zone regardless of score (re-test logic needs the level)
        zone = _ZoneLevel(
            level=spike_extreme,
            direction=direction,
            zone_ref=spike_ref,
            confirm_strength=s_strength,
            time_score=s_time,
            best_pierce=0.0,
            ticks_left=self.retest_memory_ticks,
        )
        self._level_memory.append(zone)

        # Only arm exhaustion if score meets threshold
        if score.total >= self.min_zone_score:
            self._exhaustion = direction
            self._exhaustion_ttl_remaining = self.exhaustion_ttl
            self._active_zone_score = score.total
            self.log.info(
                "Zone ARMED (score=%.1f/8 ≥ %.1f)  exhaustion=%s  active %d ticks",
                score.total, self.min_zone_score, direction.value.upper(), self.exhaustion_ttl,
            )
        else:
            self.log.info(
                "Zone SKIPPED (score=%.1f/8 < %.1f threshold)",
                score.total, self.min_zone_score,
            )

    # ------------------------------------------------------------------
    # Internal — Re-test detector
    # ------------------------------------------------------------------

    def _update_level_memory(self, price: float) -> None:
        if not self._level_memory:
            return

        updated: list[_ZoneLevel] = []
        for zone in self._level_memory:
            zone.ticks_left -= 1
            if zone.ticks_left <= 0:
                continue

            # Update pierce tracking
            pierce = self._pierce_fraction(price, zone)
            if pierce > zone.best_pierce:
                zone.best_pierce = pierce

            # Invalidate if >50% pierced (zone likely broken through)
            freshness = self._score_freshness(zone.best_pierce)
            if freshness == 0.0:
                self.log.info(
                    "Zone INVALIDATED (pierced >50%%): level=%.5f dir=%s",
                    zone.level, zone.direction.value,
                )
                continue  # drop this zone

            # Re-test proximity check
            proximity = abs(price - zone.level) / zone.level
            if proximity <= self.retest_proximity and self._exhaustion == Signal.NEUTRAL:
                score = self._compute_zone_score(zone)
                if score.total >= self.min_zone_score:
                    self._exhaustion = zone.direction
                    self._exhaustion_ttl_remaining = self.retest_ttl
                    self._active_zone_score = score.total
                    label = "support" if zone.direction == Signal.BUY else "resistance"
                    self.log.info(
                        "RE-TEST %s level=%.5f price=%.5f (%.3f%% away)  "
                        "signal=%s  |  %s  active %d ticks",
                        label, zone.level, price, proximity * 100,
                        zone.direction.value.upper(), score, self.retest_ttl,
                    )
                else:
                    self.log.info(
                        "RE-TEST rejected (score=%.1f/8 < %.1f): "
                        "level=%.5f  pierce=%.0f%%",
                        score.total, self.min_zone_score,
                        zone.level, zone.best_pierce * 100,
                    )

            updated.append(zone)

        self._level_memory = updated
