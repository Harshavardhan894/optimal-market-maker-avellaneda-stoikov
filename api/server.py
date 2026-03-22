from __future__ import annotations

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from core.order_book import LimitOrderBook
from simulator.engine import SimulationConfig, run_simulation


class SimulationRequest(BaseModel):
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
    seed: int = 42
    strategy_enabled: bool = True
    vol_ema_alpha: float = 0.12


class AddOrderRequest(BaseModel):
    price: float
    quantity: int
    is_buy: bool
    owner: str = "manual"


class CancelOrderRequest(BaseModel):
    order_id: int


class _LiveBookState:
    def __init__(self) -> None:
        self.reset()

    def reset(self) -> None:
        self.lob = LimitOrderBook()
        self.timestamp = 0
        self.last_trades = []

    def snapshot(self) -> dict:
        return {
            "timestamp": self.timestamp,
            "best_bid": self.lob.get_best_bid(),
            "best_ask": self.lob.get_best_ask(),
            "order_book": self.lob.top_levels(depth=10),
            "last_trades": self.last_trades,
        }


LIVE = _LiveBookState()


app = FastAPI(title="Optimal Market Maker API", version="1.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/health")
def health() -> dict:
    return {"status": "ok"}


@app.post("/run")
def run(req: SimulationRequest) -> dict:
    cfg = SimulationConfig(**req.model_dump())
    return run_simulation(cfg)


@app.get("/book")
def get_book() -> dict:
    return LIVE.snapshot()


@app.post("/book/reset")
def reset_book() -> dict:
    LIVE.reset()
    return LIVE.snapshot()


@app.post("/book/add_order")
def add_order(req: AddOrderRequest) -> dict:
    LIVE.timestamp += 1
    order_id = LIVE.lob.add_order(
        price=req.price,
        quantity=req.quantity,
        is_buy=req.is_buy,
        timestamp=LIVE.timestamp,
        owner=req.owner,
    )
    return {"order_id": order_id, **LIVE.snapshot()}


@app.post("/book/cancel_order")
def cancel_order(req: CancelOrderRequest) -> dict:
    ok = LIVE.lob.cancel_order(req.order_id)
    return {"cancelled": ok, **LIVE.snapshot()}


@app.post("/book/match")
def match_book() -> dict:
    LIVE.timestamp += 1
    trades = LIVE.lob.match_orders(LIVE.timestamp)
    LIVE.last_trades = [
        {
            "price": t.price,
            "quantity": t.quantity,
            "timestamp": t.timestamp,
            "buy_order_id": t.buy_order_id,
            "sell_order_id": t.sell_order_id,
            "buy_owner": t.buy_owner,
            "sell_owner": t.sell_owner,
        }
        for t in trades
    ]
    return LIVE.snapshot()
