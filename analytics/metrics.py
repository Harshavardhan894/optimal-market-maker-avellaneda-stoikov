from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Dict, List

from core.models import Trade


@dataclass
class AnalyticsEngine:
    inventory: int = 0
    cash: float = 0.0
    trade_count: int = 0
    spread_capture: float = 0.0
    pnl_series: List[float] = field(default_factory=list)
    returns: List[float] = field(default_factory=list)
    logs: List[Dict] = field(default_factory=list)

    def process_trade(self, trade: Trade, mid: float) -> None:
        if trade.buy_owner == "mm":
            self.inventory += trade.quantity
            self.cash -= trade.quantity * trade.price
            self.trade_count += 1
            self.spread_capture += max(0.0, mid - trade.price) * trade.quantity

        if trade.sell_owner == "mm":
            self.inventory -= trade.quantity
            self.cash += trade.quantity * trade.price
            self.trade_count += 1
            self.spread_capture += max(0.0, trade.price - mid) * trade.quantity

    def mark_to_market_pnl(self, mid: float) -> float:
        return self.cash + self.inventory * mid

    def record(self, timestamp: int, mid: float) -> None:
        pnl = self.mark_to_market_pnl(mid)
        if self.pnl_series:
            prev = self.pnl_series[-1]
            self.returns.append(pnl - prev)
        self.pnl_series.append(pnl)
        self.logs.append(
            {
                "timestamp": timestamp,
                "price": mid,
                "inventory": self.inventory,
                "pnl": pnl,
                "trades": self.trade_count,
            }
        )

    def sharpe(self) -> float:
        if len(self.returns) < 2:
            return 0.0
        mean_r = sum(self.returns) / len(self.returns)
        var = sum((x - mean_r) ** 2 for x in self.returns) / (len(self.returns) - 1)
        std = math.sqrt(var)
        if std == 0:
            return 0.0
        return mean_r / std

    def max_drawdown(self) -> float:
        if not self.pnl_series:
            return 0.0
        peak = self.pnl_series[0]
        max_dd = 0.0
        for p in self.pnl_series:
            peak = max(peak, p)
            max_dd = min(max_dd, p - peak)
        return max_dd

    def win_loss_ratio(self) -> float:
        if not self.returns:
            return 0.0
        wins = sum(1 for r in self.returns if r > 0)
        losses = sum(1 for r in self.returns if r < 0)
        if losses == 0:
            return float(wins)
        return wins / losses

    def summary(self, mid: float) -> Dict:
        raw_sharpe = self.sharpe()
        horizon_scale = math.sqrt(max(len(self.pnl_series), 1))
        sharpe_horizon_scaled = raw_sharpe * horizon_scale
        sharpe_annualized_252 = raw_sharpe * math.sqrt(252)
        return {
            "final_pnl": self.mark_to_market_pnl(mid),
            "inventory": self.inventory,
            "trades": self.trade_count,
            "spread_capture": self.spread_capture,
            "sharpe": raw_sharpe,
            "sharpe_horizon_scaled": sharpe_horizon_scaled,
            "sharpe_annualized_252": sharpe_annualized_252,
            "max_drawdown": self.max_drawdown(),
            "win_loss_ratio": self.win_loss_ratio(),
        }
