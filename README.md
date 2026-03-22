# Optimal Market Making System (Avellaneda–Stoikov)

A research-focused simulation platform for market making in a limit order book (LOB) environment.

The project includes:

- A matching engine with price-time priority
- A stochastic market simulator with heterogeneous trader behavior
- An Avellaneda–Stoikov-inspired market-making strategy
- Risk controls, analytics, and experiment tooling
- A FastAPI backend and React dashboard

---

## Features

### Core engine

- LOB with bid/ask books, order add/cancel/match, partial fills
- Best bid/best ask tracking
- Manual order book API for interactive testing

### Market simulation

- Random-walk price process
- Trader types: noise, momentum, informed, optional adversarial
- Tick-based event loop with matching and strategy interaction

### Strategy

- Avellaneda–Stoikov reservation pricing
- Volatility-aware pricing
- Dynamic spread control
- Inventory-aware skewing, sizing, and quote gating
- Stop-loss and inventory constraints

### Analytics

- PnL, inventory, trade count, spread capture
- Sharpe (raw), Sharpe scaled by horizon, annualized Sharpe
- Max drawdown, win/loss ratio

### Dashboard

- Price / PnL / Inventory charts
- Live metrics panel
- Manual LOB controls (add, cancel, match, reset)
- Strategy start/pause toggle
- Parameter controls and seed input
- Trade log panel

---

## Repository structure

```text
core/
simulator/
strategy/
analytics/
api/
frontend/
experiments/
benchmarks/
scripts/
```

---

### Quick start (recommended)

```bash
./scripts/dev_up.sh
./scripts/dev_status.sh
```

Open:

- http://127.0.0.1:5173

Stop services:

```bash
./scripts/dev_down.sh
```

### Manual start

Backend:

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
uvicorn api.server:app --host 127.0.0.1 --port 8000
```

Frontend:

```bash
cd frontend
npm install
npm run dev -- --host 127.0.0.1 --port 5173
```

---

## Frontend runtime modes

Set values in `frontend/.env`:

- `VITE_DEMO_MODE=true`: frontend-only demo mode (no backend dependency)
- `VITE_DEMO_MODE=false`: backend-connected mode (manual LOB APIs enabled)

Recommended backend URL:

- `VITE_API_BASE_URL=http://127.0.0.1:8000`

---

## API overview

### Simulation

- `GET /health`
- `POST /run`

### Manual LOB

- `GET /book`
- `POST /book/reset`
- `POST /book/add_order`
- `POST /book/cancel_order`
- `POST /book/match`

---

## Experiments and benchmarks

Run experiment sweeps:

```bash
python -m experiments.run_experiments
```

Run LOB performance benchmark:

```bash
python -m benchmarks.lob_benchmark
```

---

## Deployment

### Frontend (GitHub Pages)

This repository includes a Pages workflow:

- `.github/workflows/deploy-frontend-pages.yml`

After pushing to `main`, GitHub Actions can deploy the frontend to Pages.

### Backend

GitHub Pages serves static content only.

Backend-dependent features (manual LOB APIs, backend simulation mode) require deploying FastAPI separately (Render, Railway, Fly.io, VPS, etc.).

When backend is deployed, provide its URL as:

- `VITE_API_BASE_URL=https://<backend-url>`

---

## Strategy reference

Reservation price:

$$
r_t = s_t - q_t\gamma\sigma^2(T-t)
$$

Quotes:

$$
	ext{bid} = r_t - \delta_t, \quad \text{ask} = r_t + \delta_t
$$