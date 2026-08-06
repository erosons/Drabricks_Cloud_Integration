from enum import Enum


class Signal(str, Enum):
    BUY = "buy"
    SELL = "sell"
    NEUTRAL = "neutral"
