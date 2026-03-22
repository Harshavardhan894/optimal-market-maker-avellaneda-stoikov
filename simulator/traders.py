from __future__ import annotations

import random
from dataclasses import dataclass
from typing import List, Tuple


OrderIntent = Tuple[float, int, bool, str]


@dataclass
class NoiseTrader:
    arrival_prob: float = 0.8
    max_size: int = 3
    tick_size: float = 0.01

    def generate(self, mid: float) -> List[OrderIntent]:
        if random.random() > self.arrival_prob:
            return []
        side = random.choice([True, False])
        size = random.randint(1, self.max_size)
        offset_ticks = random.randint(-3, 3)
        px = max(0.01, mid + offset_ticks * self.tick_size)
        return [(px, size, side, "noise")]


@dataclass
class MomentumTrader:
    arrival_prob: float = 0.4
    max_size: int = 4
    tick_size: float = 0.01

    def generate(self, mid: float, prev_mid: float) -> List[OrderIntent]:
        if random.random() > self.arrival_prob:
            return []
        trend_up = mid > prev_mid
        side = trend_up
        size = random.randint(1, self.max_size)
        px = mid + (2 * self.tick_size if side else -2 * self.tick_size)
        px = max(0.01, px)
        return [(px, size, side, "momentum")]


@dataclass
class InformedTrader:
    arrival_prob: float = 0.08
    max_size: int = 6
    signal_strength: float = 0.5
    tick_size: float = 0.01

    def generate(self, mid: float, drift_signal: float) -> List[OrderIntent]:
        if random.random() > self.arrival_prob:
            return []
        side = drift_signal > self.signal_strength
        size = random.randint(max(2, self.max_size // 2), self.max_size)
        px = mid + (3 * self.tick_size if side else -3 * self.tick_size)
        px = max(0.01, px)
        return [(px, size, side, "informed")]


@dataclass
class AdversarialTrader:
    arrival_prob: float = 0.1
    max_size: int = 6
    tick_size: float = 0.01

    def generate(
        self,
        mid: float,
        prev_mid: float,
        mm_bid: float,
        mm_ask: float,
    ) -> List[OrderIntent]:
        if random.random() > self.arrival_prob:
            return []

        trend_up = mid > prev_mid
        is_buy = trend_up
        size = random.randint(max(2, self.max_size // 2), self.max_size)

        if is_buy:
            px = max(0.01, mm_ask + self.tick_size)
        else:
            px = max(0.01, mm_bid - self.tick_size)

        return [(px, size, is_buy, "adversarial")]
