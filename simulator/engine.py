from __future__ import annotations

import random
import math
from dataclasses import dataclass
from typing import Dict, Optional

from analytics.metrics import AnalyticsEngine
from core.order_book import LimitOrderBook
from simulator.price_model import RandomWalkPriceModel
from simulator.traders import AdversarialTrader, InformedTrader, MomentumTrader, NoiseTrader
from strategy.market_maker import AvellanedaStoikovMarketMaker, MarketMakerConfig


@dataclass
class SimulationConfig:
    ticks: int = 500
    s0: float = 100.0
    mu: float = 0.0
    sigma: float = 1.2
    dt: float = 1.0
    latency_prob: float = 0.15

    gamma: float = 0.08
    T: int = 500
    delta: float = 0.08
    max_inventory: int = 80
    order_size: int = 2
    stop_loss: float = -250.0
    enable_adversarial: bool = True
    adversarial_prob: float = 0.1
    seed: Optional[int] = 42
    strategy_enabled: bool = True
    vol_ema_alpha: float = 0.12


def run_simulation(config: SimulationConfig) -> Dict:
    random.seed(config.seed)

    lob = LimitOrderBook()
    price_model = RandomWalkPriceModel(s0=config.s0, mu=config.mu, sigma=config.sigma, dt=config.dt)
    strategy = AvellanedaStoikovMarketMaker(
        config=MarketMakerConfig(
            gamma=config.gamma,
            sigma=config.sigma,
            T=config.T,
            base_delta=config.delta,
            max_inventory=config.max_inventory,
            order_size=config.order_size,
            stop_loss=config.stop_loss,
        )
    )
    analytics = AnalyticsEngine()

    noise = NoiseTrader()
    momentum = MomentumTrader()
    informed = InformedTrader()
    adversarial = AdversarialTrader(arrival_prob=config.adversarial_prob)

    delayed_orders = []
    prev_mid = config.s0
    ewma_var = max(config.sigma ** 2, 1e-8)
    ewma_ret = 0.0

    for t in range(1, config.ticks + 1):
        # 1) Update price
        mid = price_model.step()
        d_price = mid - prev_mid
        alpha = max(0.01, min(0.9, config.vol_ema_alpha))
        ewma_var = alpha * (d_price ** 2) + (1.0 - alpha) * ewma_var
        sigma_hat = math.sqrt(max(ewma_var, 1e-8))
        ewma_ret = alpha * d_price + (1.0 - alpha) * ewma_ret
        trend_signal = math.tanh(ewma_ret / (sigma_hat + 1e-8))

        # 2) Strategy acts first so quotes are present for current-tick flow
        current_pnl = analytics.mark_to_market_pnl(mid)
        if config.strategy_enabled:
            strategy.act(
                lob,
                mid,
                analytics.inventory,
                current_pnl,
                t,
                sigma_t=sigma_hat,
                best_bid=lob.get_best_bid(),
                best_ask=lob.get_best_ask(),
                trend_signal=trend_signal,
            )

        # 3) Generate trader orders
        intents = []
        intents.extend(noise.generate(mid))
        intents.extend(momentum.generate(mid, prev_mid))
        drift_signal = 1.0 if (mid - prev_mid) > 0 else 0.0
        intents.extend(informed.generate(mid, drift_signal))
        if config.enable_adversarial:
            mm_r = strategy.reservation_price(mid, analytics.inventory, t, sigma_t=sigma_hat)
            mm_d = strategy.half_spread(t, sigma_t=sigma_hat)
            mm_bid = max(0.01, mm_r - mm_d)
            mm_ask = max(0.01, mm_r + mm_d)
            intents.extend(adversarial.generate(mid, prev_mid, mm_bid, mm_ask))

        # 4) Send orders to LOB (with latency feature)
        for px, qty, side, owner in intents:
            if random.random() < config.latency_prob:
                delayed_orders.append((t + 1, px, qty, side, owner))
            else:
                lob.add_order(px, qty, side, t, owner)

        ready = [x for x in delayed_orders if x[0] <= t]
        delayed_orders = [x for x in delayed_orders if x[0] > t]
        for _, px, qty, side, owner in ready:
            lob.add_order(px, qty, side, t, owner)

        # 5) Match trades
        trades = lob.match_orders(t)
        for tr in trades:
            analytics.process_trade(tr, mid)
            mm_vs_adv = (tr.buy_owner == "mm" and tr.sell_owner == "adversarial") or (
                tr.sell_owner == "mm" and tr.buy_owner == "adversarial"
            )
            mm_vs_inf = (tr.buy_owner == "mm" and tr.sell_owner == "informed") or (
                tr.sell_owner == "mm" and tr.buy_owner == "informed"
            )
            if mm_vs_adv:
                analytics.cash -= 6.0 * config.sigma * tr.quantity
            elif mm_vs_inf:
                analytics.cash -= 0.1 * config.sigma * tr.quantity

        # 6) Record metrics
        analytics.record(t, mid)
        prev_mid = mid

    return {
        "summary": analytics.summary(prev_mid),
        "series": analytics.logs,
        "order_book": lob.top_levels(depth=10),
    }
