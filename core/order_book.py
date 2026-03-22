from __future__ import annotations

import heapq
from collections import defaultdict, deque
from typing import Deque, Dict, List, Optional

from .models import Order, Trade


class LimitOrderBook:
    def __init__(self) -> None:
        self.bids: Dict[float, Deque[Order]] = defaultdict(deque)
        self.asks: Dict[float, Deque[Order]] = defaultdict(deque)
        self.bid_heap: List[float] = []
        self.ask_heap: List[float] = []
        self.order_index: Dict[int, Order] = {}
        self._order_id = 1

    def _next_id(self) -> int:
        oid = self._order_id
        self._order_id += 1
        return oid

    def add_order(
        self,
        price: float,
        quantity: int,
        is_buy: bool,
        timestamp: int,
        owner: str = "external",
    ) -> int:
        order = Order(
            id=self._next_id(),
            price=round(price, 4),
            quantity=quantity,
            is_buy=is_buy,
            timestamp=timestamp,
            owner=owner,
        )
        self.order_index[order.id] = order

        if is_buy:
            if order.price not in self.bids:
                heapq.heappush(self.bid_heap, -order.price)
            self.bids[order.price].append(order)
        else:
            if order.price not in self.asks:
                heapq.heappush(self.ask_heap, order.price)
            self.asks[order.price].append(order)

        return order.id

    def cancel_order(self, order_id: int) -> bool:
        order = self.order_index.get(order_id)
        if not order or not order.active:
            return False
        order.active = False
        return True

    def _clean_price_level(self, is_buy: bool, price: float) -> None:
        side = self.bids if is_buy else self.asks
        if price not in side:
            return
        queue = side[price]
        while queue and (not queue[0].active or queue[0].quantity <= 0):
            queue.popleft()
        if not queue:
            del side[price]

    def _best_bid_price(self) -> Optional[float]:
        while self.bid_heap:
            price = -self.bid_heap[0]
            self._clean_price_level(True, price)
            if price in self.bids and self.bids[price]:
                return price
            heapq.heappop(self.bid_heap)
        return None

    def _best_ask_price(self) -> Optional[float]:
        while self.ask_heap:
            price = self.ask_heap[0]
            self._clean_price_level(False, price)
            if price in self.asks and self.asks[price]:
                return price
            heapq.heappop(self.ask_heap)
        return None

    def get_best_bid(self) -> Optional[float]:
        return self._best_bid_price()

    def get_best_ask(self) -> Optional[float]:
        return self._best_ask_price()

    def match_orders(self, timestamp: int) -> List[Trade]:
        trades: List[Trade] = []

        while True:
            best_bid = self._best_bid_price()
            best_ask = self._best_ask_price()

            if best_bid is None or best_ask is None or best_bid < best_ask:
                break

            buy_order = self.bids[best_bid][0]
            sell_order = self.asks[best_ask][0]

            qty = min(buy_order.quantity, sell_order.quantity)
            trade_price = sell_order.price if buy_order.timestamp > sell_order.timestamp else buy_order.price

            buy_order.quantity -= qty
            sell_order.quantity -= qty

            trades.append(
                Trade(
                    price=trade_price,
                    quantity=qty,
                    timestamp=timestamp,
                    buy_order_id=buy_order.id,
                    sell_order_id=sell_order.id,
                    buy_owner=buy_order.owner,
                    sell_owner=sell_order.owner,
                )
            )

            if buy_order.quantity <= 0:
                buy_order.active = False
                self.bids[best_bid].popleft()
            if sell_order.quantity <= 0:
                sell_order.active = False
                self.asks[best_ask].popleft()

            self._clean_price_level(True, best_bid)
            self._clean_price_level(False, best_ask)

        return trades

    def top_levels(self, depth: int = 10) -> dict:
        bid_levels = sorted((p, q) for p, q in self._aggregate(self.bids).items())[-depth:]
        ask_levels = sorted((p, q) for p, q in self._aggregate(self.asks).items())[:depth]
        return {
            "bids": [{"price": p, "quantity": q} for p, q in reversed(bid_levels)],
            "asks": [{"price": p, "quantity": q} for p, q in ask_levels],
        }

    def _aggregate(self, side: Dict[float, Deque[Order]]) -> Dict[float, int]:
        out: Dict[float, int] = {}
        for price, queue in side.items():
            qty = sum(o.quantity for o in queue if o.active and o.quantity > 0)
            if qty > 0:
                out[price] = qty
        return out
