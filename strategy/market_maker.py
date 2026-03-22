from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import List

from core.order_book import LimitOrderBook


@dataclass
class MarketMakerConfig:
    gamma: float = 0.08
    sigma: float = 1.2
    T: int = 1_000
    base_delta: float = 0.08
    max_inventory: int = 80
    order_size: int = 2
    stale_after: int = 8
    stop_loss: float = -250.0
    inventory_soft_limit_ratio: float = 0.35
    inventory_hard_limit_ratio: float = 0.75
    unwind_multiplier: float = 2.0
    skew_per_inventory: float = 0.002
    volatility_floor: float = 0.2
    volatility_ceiling: float = 3.0
    spread_vol_multiplier: float = 0.15
    min_half_spread: float = 0.01
    max_half_spread: float = 1.0
    market_spread_weight: float = 0.5
    trend_skew_strength: float = 0.12
    toxicity_threshold: float = 0.45
    toxicity_spread_multiplier: float = 1.8
    trend_size_multiplier: float = 1.2
    high_toxicity_threshold: float = 0.25
    high_toxicity_spread_boost: float = 1.35
    high_toxicity_size_factor: float = 0.55
    one_sided_toxic_mode: bool = True


@dataclass
class AvellanedaStoikovMarketMaker:
    config: MarketMakerConfig
    active_order_ids: List[int] = field(default_factory=list)
    active: bool = True

    def _effective_sigma(self, sigma_t: float | None = None) -> float:
        sigma = self.config.sigma if sigma_t is None else sigma_t
        return max(self.config.volatility_floor, min(self.config.volatility_ceiling, sigma))

    def reservation_price(self, s_t: float, q_t: int, t: int, sigma_t: float | None = None) -> float:
        sigma = self._effective_sigma(sigma_t)
        tau = max(self.config.T - t, 0)
        return s_t - q_t * self.config.gamma * (sigma ** 2) * tau / max(self.config.T, 1)

    def half_spread(self, t: int, sigma_t: float | None = None, market_spread: float | None = None) -> float:
        sigma = self._effective_sigma(sigma_t)
        tau = max(self.config.T - t, 0)
        inventory_risk_premium = 0.5 * self.config.gamma * (sigma ** 2) * tau / max(self.config.T, 1)
        vol_component = self.config.spread_vol_multiplier * sigma
        d = self.config.base_delta + inventory_risk_premium + vol_component
        if market_spread is not None:
            d += self.config.market_spread_weight * max(0.0, market_spread) / 2.0
        return max(self.config.min_half_spread, min(self.config.max_half_spread, d))

    def cancel_stale_orders(self, lob: LimitOrderBook) -> None:
        retained: List[int] = []
        for oid in self.active_order_ids:
            order = lob.order_index.get(oid)
            if order and order.active:
                lob.cancel_order(oid)
            if order and order.active:
                retained.append(oid)
        self.active_order_ids = retained

    def act(
        self,
        lob: LimitOrderBook,
        mid: float,
        inventory: int,
        pnl: float,
        t: int,
        sigma_t: float | None = None,
        best_bid: float | None = None,
        best_ask: float | None = None,
        trend_signal: float | None = None,
    ) -> None:
        if pnl <= self.config.stop_loss:
            self.active = False
        if not self.active:
            self.cancel_stale_orders(lob)
            return

        self.cancel_stale_orders(lob)
        market_spread = None
        if best_bid is not None and best_ask is not None and best_ask >= best_bid:
            market_spread = best_ask - best_bid

        sigma_eff = self._effective_sigma(sigma_t)
        trend = max(-1.0, min(1.0, trend_signal or 0.0))

        # Volatility-aware reservation price + trend skew:
        # uptrend -> quote higher to avoid getting run over on asks
        # downtrend -> quote lower to avoid catching falling knife on bids
        r_t = self.reservation_price(mid, inventory, t, sigma_t=sigma_t)
        r_t += self.config.trend_skew_strength * sigma_eff * trend

        inv_abs = abs(inventory)
        max_inv = max(self.config.max_inventory, 1)
        inv_ratio = min(inv_abs / max_inv, 1.5)
        d = self.half_spread(t, sigma_t=sigma_t, market_spread=market_spread) * (1.0 + inv_ratio)

        # Toxicity proxy from short-term trend + volatility.
        tox_raw = abs(trend) * sigma_eff - self.config.toxicity_threshold
        toxicity = max(0.0, tox_raw) / max(1.0, sigma_eff)
        d *= 1.0 + self.config.toxicity_spread_multiplier * toxicity

        high_toxicity = toxicity >= self.config.high_toxicity_threshold
        if high_toxicity:
            d *= self.config.high_toxicity_spread_boost

        # Extra skew to reinforce inventory mean reversion.
        # inventory > 0 -> shift both quotes down (sell easier, buy harder)
        # inventory < 0 -> shift both quotes up (buy easier, sell harder)
        skew = self.config.skew_per_inventory * inventory

        bid_px = max(0.01, r_t - d - skew)
        ask_px = max(0.01, r_t + d - skew)

        base_size = max(1, self.config.order_size)
        buy_size = base_size
        sell_size = base_size

        if inventory > 0:
            sell_size = max(base_size, int(math.ceil(base_size * (1.0 + self.config.unwind_multiplier * inv_ratio))))
            buy_size = max(1, int(math.floor(base_size * (1.0 - 0.8 * inv_ratio))))
        elif inventory < 0:
            buy_size = max(base_size, int(math.ceil(base_size * (1.0 + self.config.unwind_multiplier * inv_ratio))))
            sell_size = max(1, int(math.floor(base_size * (1.0 - 0.8 * inv_ratio))))

        # Trend-aware sizing: quote heavier with trend, lighter against trend.
        if trend > 0:
            buy_size = max(1, int(math.ceil(buy_size * (1.0 + self.config.trend_size_multiplier * abs(trend)))))
            sell_size = max(1, int(math.floor(sell_size * (1.0 - 0.7 * abs(trend)))))
        elif trend < 0:
            sell_size = max(1, int(math.ceil(sell_size * (1.0 + self.config.trend_size_multiplier * abs(trend)))))
            buy_size = max(1, int(math.floor(buy_size * (1.0 - 0.7 * abs(trend)))))

        if high_toxicity:
            buy_size = max(1, int(math.floor(buy_size * self.config.high_toxicity_size_factor)))
            sell_size = max(1, int(math.floor(sell_size * self.config.high_toxicity_size_factor)))

        allow_buy = inventory < self.config.max_inventory
        allow_sell = inventory > -self.config.max_inventory

        # Soft-limit gating: stop adding inventory in the wrong direction.
        if inv_ratio >= self.config.inventory_soft_limit_ratio:
            if inventory > 0:
                allow_buy = False
            elif inventory < 0:
                allow_sell = False

        # Hard-limit emergency mode: unwind one-sided only.
        if inv_ratio >= self.config.inventory_hard_limit_ratio:
            if inventory > 0:
                allow_buy = False
                allow_sell = True
            elif inventory < 0:
                allow_sell = False
                allow_buy = True

        # Toxicity gating against adverse selection.
        # In strong uptrend, do not continue offering asks when already short.
        # In strong downtrend, do not continue bidding when already long.
        if toxicity > 0.0 and abs(trend) > 0.3:
            if trend > 0 and inventory <= 0:
                allow_sell = False
            if trend < 0 and inventory >= 0:
                allow_buy = False

        if high_toxicity and self.config.one_sided_toxic_mode:
            if inventory == 0:
                if trend > 0:
                    allow_sell = False
                elif trend < 0:
                    allow_buy = False

        if allow_buy:
            bid_id = lob.add_order(
                price=bid_px,
                quantity=buy_size,
                is_buy=True,
                timestamp=t,
                owner="mm",
            )
            self.active_order_ids.append(bid_id)

        if allow_sell:
            ask_id = lob.add_order(
                price=ask_px,
                quantity=sell_size,
                is_buy=False,
                timestamp=t,
                owner="mm",
            )
            self.active_order_ids.append(ask_id)
