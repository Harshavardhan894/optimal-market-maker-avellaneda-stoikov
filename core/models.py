from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class Order:
    id: int
    price: float
    quantity: int
    is_buy: bool
    timestamp: int
    owner: str = "external"
    active: bool = True


@dataclass
class Trade:
    price: float
    quantity: int
    timestamp: int
    buy_order_id: int
    sell_order_id: int
    buy_owner: str = field(default="external")
    sell_owner: str = field(default="external")
