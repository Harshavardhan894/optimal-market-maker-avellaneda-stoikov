from __future__ import annotations

import random
from dataclasses import dataclass


@dataclass
class RandomWalkPriceModel:
    s0: float = 100.0
    mu: float = 0.0
    sigma: float = 1.0
    dt: float = 1.0

    def __post_init__(self) -> None:
        self.s = self.s0

    def step(self) -> float:
        eps = random.gauss(0.0, 1.0)
        self.s = self.s + self.mu * self.dt + self.sigma * eps
        self.s = max(0.01, self.s)
        return self.s
