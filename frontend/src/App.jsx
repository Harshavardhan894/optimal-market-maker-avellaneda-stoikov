import { useEffect, useMemo, useRef, useState } from 'react'
import { Line } from 'react-chartjs-2'
import {
  Chart as ChartJS,
  CategoryScale,
  LinearScale,
  PointElement,
  LineElement,
  Title,
  Tooltip,
  Legend
} from 'chart.js'

ChartJS.register(CategoryScale, LinearScale, PointElement, LineElement, Title, Tooltip, Legend)

const ENV_API = String(import.meta.env.VITE_API_BASE_URL || '').trim()
const ENV_DEMO_MODE = String(import.meta.env.VITE_DEMO_MODE || 'false') === 'true'
const DEFAULT_API = ENV_API || (import.meta.env.DEV ? 'http://localhost:8000' : '')

function createSeededRng(seed) {
  let state = (Number(seed) || 1) >>> 0
  return () => {
    state = (1664525 * state + 1013904223) >>> 0
    return state / 4294967296
  }
}

function generateDemoResult(cfg) {
  const rand = createSeededRng(cfg.seed)
  const ticks = Math.max(20, Number(cfg.ticks || 500))
  let price = 100
  let inventory = 0
  let cash = 0
  let trades = 0
  let spreadCapture = 0
  const series = []
  const rets = []
  let lastPnl = 0

  for (let t = 1; t <= ticks; t += 1) {
    const eps = (rand() - 0.5) * 2
    price = Math.max(1, price + 0.03 + Number(cfg.sigma || 1.2) * eps)

    const r = price - inventory * Number(cfg.gamma || 0.08) * (Number(cfg.sigma || 1.2) ** 2)
    const d = Math.max(0.01, Number(cfg.delta || 0.08))
    const bid = r - d
    const ask = r + d

    if (rand() < 0.55) {
      inventory += 1
      cash -= bid
      spreadCapture += Math.max(0, price - bid)
      trades += 1
    }
    if (rand() < 0.55) {
      inventory -= 1
      cash += ask
      spreadCapture += Math.max(0, ask - price)
      trades += 1
    }

    const pnl = cash + inventory * price
    rets.push(pnl - lastPnl)
    lastPnl = pnl

    series.push({ timestamp: t, price, inventory, pnl, trades })
  }

  const mean = rets.reduce((a, b) => a + b, 0) / Math.max(1, rets.length)
  const variance = rets.reduce((a, x) => a + (x - mean) ** 2, 0) / Math.max(1, rets.length - 1)
  const std = Math.sqrt(variance)
  const sharpe = std > 0 ? mean / std : 0
  const sharpeHorizonScaled = sharpe * Math.sqrt(Math.max(series.length, 1))
  const sharpeAnnualized252 = sharpe * Math.sqrt(252)

  let peak = -Infinity
  let maxDrawdown = 0
  for (const p of series.map((x) => x.pnl)) {
    peak = Math.max(peak, p)
    maxDrawdown = Math.min(maxDrawdown, p - peak)
  }

  const wins = rets.filter((x) => x > 0).length
  const losses = rets.filter((x) => x < 0).length
  const winLoss = losses > 0 ? wins / losses : wins

  const mid = price
  const order_book = {
    bids: Array.from({ length: 10 }).map((_, i) => ({ price: mid - 0.01 * (i + 1), quantity: 2 + (i % 4) })),
    asks: Array.from({ length: 10 }).map((_, i) => ({ price: mid + 0.01 * (i + 1), quantity: 2 + ((i + 1) % 4) }))
  }

  return {
    summary: {
      final_pnl: series.at(-1)?.pnl || 0,
      inventory,
      trades,
      spread_capture: spreadCapture,
      sharpe,
      sharpe_horizon_scaled: sharpeHorizonScaled,
      sharpe_annualized_252: sharpeAnnualized252,
      max_drawdown: maxDrawdown,
      win_loss_ratio: winLoss
    },
    series,
    order_book
  }
}

export default function App() {
  const [apiBase, setApiBase] = useState(() => localStorage.getItem('apiBaseUrl') || DEFAULT_API)
  const [loading, setLoading] = useState(false)
  const [result, setResult] = useState(null)
  const [error, setError] = useState('')
  const [resultSource, setResultSource] = useState('none')
  const [cfg, setCfg] = useState({
    ticks: 500,
    sigma: 1.0,
    gamma: 0.12,
    delta: 0.32,
    max_inventory: 30,
    stop_loss: -250,
    seed: 42,
    enable_adversarial: false
  })
  const [strategyEnabled, setStrategyEnabled] = useState(true)
  const [playIdx, setPlayIdx] = useState(0)
  const [autoPlay, setAutoPlay] = useState(false)
  const [manual, setManual] = useState({ price: 100, quantity: 1 })
  const [cancelId, setCancelId] = useState('')
  const [book, setBook] = useState(null)
  const [bookStatus, setBookStatus] = useState('')
  const [lastOrderInfo, setLastOrderInfo] = useState(null)
  const [recentTrades, setRecentTrades] = useState([])
  const [orderMeta, setOrderMeta] = useState({})
  const [tradeLog, setTradeLog] = useState([])
  const [uiInventory, setUiInventory] = useState(0)
  const [uiCash, setUiCash] = useState(0)
  const [toast, setToast] = useState({ message: '', type: 'info', visible: false })
  const toastTimerRef = useRef(null)
  const isDemoMode = ENV_DEMO_MODE && !apiBase

  const showToast = (message, type = 'info') => {
    if (toastTimerRef.current) {
      clearTimeout(toastTimerRef.current)
    }
    setToast({ message, type, visible: true })
    toastTimerRef.current = setTimeout(() => {
      setToast((prev) => ({ ...prev, visible: false }))
    }, 2200)
  }

  const callApi = async (path, init = {}) => {
    if (!apiBase) throw new Error('Backend API URL not configured')
    const res = await fetch(`${apiBase}${path}`, init)
    if (!res.ok) throw new Error(`API error: ${res.status}`)
    return res.json()
  }

  const refreshBook = async () => {
    if (isDemoMode) {
      setBookStatus('Manual order controls require backend mode (set VITE_DEMO_MODE=false).')
      showToast('Refresh Book clicked (backend mode required)', 'warn')
      return
    }
    try {
      const data = await callApi('/book')
      setBook(data)
      setBookStatus('Book refreshed')
      showToast('Book refreshed', 'success')
    } catch {
      setBookStatus('Unable to load book from backend')
      showToast('Refresh Book failed', 'error')
    }
  }

  const addManualOrder = async (isBuy) => {
    if (isDemoMode) {
      setBookStatus('Manual order controls require backend mode (set VITE_DEMO_MODE=false).')
      showToast(`${isBuy ? 'Add Buy Order' : 'Add Sell Order'} clicked (backend mode required)`, 'warn')
      return
    }
    try {
      const data = await callApi('/book/add_order', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          price: Number(manual.price),
          quantity: Number(manual.quantity),
          is_buy: isBuy,
          owner: 'ui'
        })
      })
      setBook(data)
      setOrderMeta((prev) => ({ ...prev, [data.order_id]: { side: isBuy ? 'buy' : 'sell' } }))
      setLastOrderInfo({
        orderId: data.order_id,
        side: isBuy ? 'BUY' : 'SELL',
        price: Number(manual.price),
        quantity: Number(manual.quantity)
      })
      setBookStatus(`Added ${isBuy ? 'BUY' : 'SELL'} order #${data.order_id}`)
      showToast(`Added ${isBuy ? 'BUY' : 'SELL'} order #${data.order_id}`, 'success')
    } catch {
      setBookStatus('Failed to add order')
      showToast('Add order failed', 'error')
    }
  }

  const cancelManualOrder = async () => {
    if (isDemoMode) {
      setBookStatus('Manual order controls require backend mode (set VITE_DEMO_MODE=false).')
      showToast('Cancel Order clicked (backend mode required)', 'warn')
      return
    }
    try {
      const data = await callApi('/book/cancel_order', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ order_id: Number(cancelId) })
      })
      setBook(data)
      setBookStatus(data.cancelled ? 'Order cancelled' : 'Order not found/already inactive')
      showToast(data.cancelled ? `Cancelled order #${cancelId}` : `Cancel failed for #${cancelId}`, data.cancelled ? 'success' : 'warn')
    } catch {
      setBookStatus('Failed to cancel order')
      showToast('Cancel order failed', 'error')
    }
  }

  const matchManual = async () => {
    if (isDemoMode) {
      setBookStatus('Manual order controls require backend mode (set VITE_DEMO_MODE=false).')
      showToast('Match Now clicked (backend mode required)', 'warn')
      return
    }
    try {
      const data = await callApi('/book/match', { method: 'POST' })
      setBook(data)
      setRecentTrades(data.last_trades || [])
      let inv = uiInventory
      let cash = uiCash
      const now = new Date().toLocaleTimeString()
      const newRows = []

      for (const t of data.last_trades || []) {
        const buyMine = orderMeta[t.buy_order_id]?.side === 'buy'
        const sellMine = orderMeta[t.sell_order_id]?.side === 'sell'

        if (buyMine) {
          const impact = -(Number(t.price) * Number(t.quantity))
          inv += Number(t.quantity)
          cash += impact
          newRows.push({ time: now, side: 'BUY', price: Number(t.price), qty: Number(t.quantity), pnlImpact: impact })
        }
        if (sellMine) {
          const impact = Number(t.price) * Number(t.quantity)
          inv -= Number(t.quantity)
          cash += impact
          newRows.push({ time: now, side: 'SELL', price: Number(t.price), qty: Number(t.quantity), pnlImpact: impact })
        }
      }

      setUiInventory(inv)
      setUiCash(cash)
      setTradeLog((prev) => [...newRows, ...prev].slice(0, 60))
      setBookStatus(`Matched ${data.last_trades?.length || 0} trades`)
      showToast(`Matched ${data.last_trades?.length || 0} trades`, 'success')
    } catch {
      setBookStatus('Failed to match orders')
      showToast('Match Now failed', 'error')
    }
  }

  const resetManual = async () => {
    if (isDemoMode) {
      setBookStatus('Manual order controls require backend mode (set VITE_DEMO_MODE=false).')
      showToast('Reset Book clicked (backend mode required)', 'warn')
      return
    }
    try {
      const data = await callApi('/book/reset', { method: 'POST' })
      setBook(data)
      setLastOrderInfo(null)
      setRecentTrades([])
      setOrderMeta({})
      setTradeLog([])
      setUiInventory(0)
      setUiCash(0)
      setBookStatus('Manual book reset')
      showToast('Manual book reset', 'success')
    } catch {
      setBookStatus('Failed to reset manual book')
      showToast('Reset Book failed', 'error')
    }
  }

  useEffect(() => {
    if (apiBase) {
      localStorage.setItem('apiBaseUrl', apiBase)
    } else {
      localStorage.removeItem('apiBaseUrl')
    }
  }, [apiBase])

  useEffect(() => {
    refreshBook()
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [isDemoMode, apiBase])

  useEffect(() => () => {
    if (toastTimerRef.current) clearTimeout(toastTimerRef.current)
  }, [])

  useEffect(() => {
    if (!autoPlay || !result?.series?.length) return
    const id = setInterval(() => {
      setPlayIdx((idx) => {
        const next = idx + 1
        if (next >= result.series.length) {
          setAutoPlay(false)
          return result.series.length - 1
        }
        return next
      })
    }, 100)
    return () => clearInterval(id)
  }, [autoPlay, result])

  const run = async () => {
    setLoading(true)
    setError('')
    showToast('Run Simulation started', 'info')
    const payload = { ...cfg, strategy_enabled: strategyEnabled }
    if (isDemoMode) {
      const demo = generateDemoResult(cfg)
      setResult(demo)
      setResultSource('demo-config')
      setPlayIdx(0)
      setAutoPlay(true)
      showToast('Run Simulation completed (demo mode)', 'success')
      setLoading(false)
      return
    }
    try {
      const response = await fetch(`${apiBase}/run`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(payload)
      })
      if (!response.ok) {
        throw new Error(`API error: ${response.status}`)
      }
      const data = await response.json()
      setResult(data)
      setResultSource('backend')
      setPlayIdx(0)
      setAutoPlay(true)
      showToast('Run Simulation completed', 'success')
    } catch (e) {
      setError('Backend unavailable. Showing demo mode results.')
      const demo = generateDemoResult(cfg)
      setResult(demo)
      setResultSource('demo-fallback')
      setPlayIdx(0)
      setAutoPlay(true)
      showToast('Backend unavailable; using demo fallback', 'warn')
    } finally {
      setLoading(false)
    }
  }

  const visibleSeries = useMemo(() => {
    if (!result?.series?.length) return []
    return result.series.slice(0, playIdx + 1)
  }, [result, playIdx])

  const labels = useMemo(() => visibleSeries.map((x) => x.timestamp), [visibleSeries])

  const priceData = useMemo(
    () => ({
      labels,
      datasets: [{ label: 'Price', data: visibleSeries.map((x) => x.price), borderColor: '#60a5fa' }]
    }),
    [labels, visibleSeries]
  )

  const pnlData = useMemo(
    () => ({
      labels,
      datasets: [{ label: 'PnL', data: visibleSeries.map((x) => x.pnl), borderColor: '#34d399' }]
    }),
    [labels, visibleSeries]
  )

  const invData = useMemo(
    () => ({
      labels,
      datasets: [{ label: 'Inventory', data: visibleSeries.map((x) => x.inventory), borderColor: '#f59e0b' }]
    }),
    [labels, visibleSeries]
  )

  const simPoint = visibleSeries.length ? visibleSeries[visibleSeries.length - 1] : null
  const manualMid = book?.best_bid != null && book?.best_ask != null ? (book.best_bid + book.best_ask) / 2 : null
  const manualSpread = book?.best_bid != null && book?.best_ask != null ? book.best_ask - book.best_bid : null
  const manualPnL = manualMid != null ? uiCash + uiInventory * manualMid : uiCash
  const liveMid = simPoint?.price ?? manualMid
  const liveInventory = simPoint?.inventory ?? uiInventory
  const livePnL = simPoint?.pnl ?? manualPnL
  const liveSpread = manualSpread
  const riskLabel = Math.abs(liveInventory) >= 50 ? 'High' : Math.abs(liveInventory) >= 20 ? 'Moderate' : 'Safe'
  const riskColor = riskLabel === 'High' ? '#ef4444' : riskLabel === 'Moderate' ? '#f59e0b' : '#22c55e'

  return (
    <div className="shell">
      <header>
        <h1>Optimal Market Maker Dashboard</h1>
      </header>

      <section className="card metrics-grid">
        <div><strong>PnL</strong><div>{livePnL != null ? livePnL.toFixed(2) : '-'}</div></div>
        <div><strong>Inventory (q)</strong><div>{liveInventory ?? '-'}</div></div>
        <div><strong>Mid Price</strong><div>{liveMid != null ? liveMid.toFixed(2) : '-'}</div></div>
        <div><strong>Spread</strong><div>{liveSpread != null ? liveSpread.toFixed(4) : '-'}</div></div>
        <div><strong>Risk</strong><div style={{ color: riskColor }}>{riskLabel}</div></div>
      </section>

      <section className="card controls">
        <label>Ticks<input type="number" value={cfg.ticks} onChange={(e) => setCfg({ ...cfg, ticks: Number(e.target.value) })} /></label>
        <label>Seed<input type="number" value={cfg.seed} onChange={(e) => setCfg({ ...cfg, seed: Number(e.target.value) })} /></label>
        <label>Max Inventory<input type="number" min="5" max="200" value={cfg.max_inventory} onChange={(e) => setCfg({ ...cfg, max_inventory: Number(e.target.value) })} /></label>
        <label>
          Adversarial Trader
          <input type="checkbox" checked={cfg.enable_adversarial} onChange={(e) => setCfg({ ...cfg, enable_adversarial: e.target.checked })} />
        </label>
        <label>
          Sigma: {cfg.sigma.toFixed(2)}
          <input type="range" min="0.1" max="3" step="0.01" value={cfg.sigma} onChange={(e) => setCfg({ ...cfg, sigma: Number(e.target.value) })} />
        </label>
        <label>
          Gamma: {cfg.gamma.toFixed(2)}
          <input type="range" min="0" max="0.8" step="0.01" value={cfg.gamma} onChange={(e) => setCfg({ ...cfg, gamma: Number(e.target.value) })} />
        </label>
        <label>
          Delta: {cfg.delta.toFixed(2)}
          <input type="range" min="0.01" max="0.5" step="0.01" value={cfg.delta} onChange={(e) => setCfg({ ...cfg, delta: Number(e.target.value) })} />
        </label>
        <button onClick={run} disabled={loading}>{loading ? 'Running...' : 'Run Simulation'}</button>
        <button onClick={() => setStrategyEnabled(true)}>▶ Start Strategy</button>
        <button onClick={() => setStrategyEnabled(false)}>⏸ Pause Strategy</button>
        <button onClick={() => setAutoPlay((v) => !v)}>{autoPlay ? 'Pause Replay' : 'Play Replay'}</button>
      </section>

      <section className="card">
        Strategy state: <strong>{strategyEnabled ? 'Running' : 'Paused'}</strong>
      </section>

      <section className="card">
        Mode: <strong>{isDemoMode ? 'Demo mode (no backend)' : 'Backend mode'}</strong>
        {' | '}Result source: <strong>{resultSource}</strong>
        {' | '}API: <strong>{apiBase || 'not set'}</strong>
        <div style={{ marginTop: 8, display: 'flex', gap: 8, alignItems: 'center', flexWrap: 'wrap' }}>
          <input
            type="text"
            placeholder="https://your-backend-url"
            value={apiBase}
            onChange={(e) => setApiBase(e.target.value.trim())}
            style={{ minWidth: 320 }}
          />
          <button onClick={() => setApiBase('')}>Use Demo</button>
        </div>
      </section>

      <section className="card manual-controls">
        <h3>Manual LOB Controls</h3>
        <div className="manual-grid">
          <label>Price<input type="number" step="0.01" value={manual.price} onChange={(e) => setManual({ ...manual, price: Number(e.target.value) })} /></label>
          <label>Quantity<input type="number" min="1" value={manual.quantity} onChange={(e) => setManual({ ...manual, quantity: Number(e.target.value) })} /></label>
          <button onClick={() => addManualOrder(true)}>Add Buy Order</button>
          <button onClick={() => addManualOrder(false)}>Add Sell Order</button>
          <label>Cancel Order ID<input type="number" value={cancelId} onChange={(e) => setCancelId(e.target.value)} /></label>
          <button onClick={cancelManualOrder}>Cancel Order</button>
          <button onClick={matchManual}>Match Now</button>
          <button onClick={refreshBook}>Refresh Book</button>
          <button onClick={resetManual}>Reset Book</button>
        </div>
        {bookStatus && <div className="manual-status">{bookStatus}</div>}
        {lastOrderInfo && (
          <div className="manual-status">
            Last order: #{lastOrderInfo.orderId} ({lastOrderInfo.side}) @ {lastOrderInfo.price.toFixed(2)} × {lastOrderInfo.quantity}
          </div>
        )}
        {recentTrades.length > 0 && (
          <div className="manual-status">
            Recent matches:
            {recentTrades.map((t, i) => (
              <div key={`rt-${i}`}>
                trade {i + 1}: price {Number(t.price).toFixed(2)} × {t.quantity} | buy_order_id #{t.buy_order_id} | sell_order_id #{t.sell_order_id}
              </div>
            ))}
          </div>
        )}
        {book && (
          <div className="book">
            <div>
              <h4>Manual Bids</h4>
              {(book.order_book?.bids || []).map((b, i) => <div key={`mb-${i}`}>{b.price.toFixed(2)} × {b.quantity}</div>)}
            </div>
            <div>
              <h4>Manual Asks</h4>
              {(book.order_book?.asks || []).map((a, i) => <div key={`ma-${i}`}>{a.price.toFixed(2)} × {a.quantity}</div>)}
            </div>
          </div>
        )}
      </section>

      {error && <section className="card" style={{ borderColor: '#ef4444' }}>{error}</section>}

      {toast.visible && (
        <div className={`toast ${toast.type}`}>
          {toast.message}
        </div>
      )}

      <section className="card trade-log">
        <h3>Trade Log</h3>
        <div className="log-head">
          <span>time</span><span>buy/sell</span><span>price</span><span>qty</span><span>pnl impact</span>
        </div>
        {tradeLog.length === 0 ? (
          <div className="log-row">No manual trades yet.</div>
        ) : tradeLog.map((r, i) => (
          <div className="log-row" key={`log-${i}`}>
            <span>{r.time}</span><span>{r.side}</span><span>{r.price.toFixed(2)}</span><span>{r.qty}</span><span>{r.pnlImpact.toFixed(2)}</span>
          </div>
        ))}
      </section>

      {result && (
        <>
          <section className="grid">
            <div className="card"><h3>Price</h3><Line data={priceData} /></div>
            <div className="card"><h3>PnL</h3><Line data={pnlData} /></div>
            <div className="card"><h3>Inventory</h3><Line data={invData} /></div>
            <div className="card">
              <h3>Order Book (Top 10)</h3>
              <div className="book">
                <div>
                  <h4>Bids</h4>
                  {(result.order_book?.bids || []).map((b, i) => <div key={`b-${i}`}>{b.price.toFixed(2)} × {b.quantity}</div>)}
                </div>
                <div>
                  <h4>Asks</h4>
                  {(result.order_book?.asks || []).map((a, i) => <div key={`a-${i}`}>{a.price.toFixed(2)} × {a.quantity}</div>)}
                </div>
              </div>
            </div>
          </section>

          <section className="card summary">
            <h3>Summary</h3>
            <div>Final PnL: {result.summary.final_pnl.toFixed(2)}</div>
            <div>Inventory: {result.summary.inventory}</div>
            <div>Trades: {result.summary.trades}</div>
            <div>Sharpe (raw): {result.summary.sharpe.toFixed(3)}</div>
            <div>Sharpe (√ticks): {result.summary.sharpe_horizon_scaled?.toFixed(3) ?? '-'}</div>
            <div>Sharpe (annualized 252): {result.summary.sharpe_annualized_252?.toFixed(3) ?? '-'}</div>
            <div>Max Drawdown: {result.summary.max_drawdown.toFixed(2)}</div>
            <div>Win/Loss: {result.summary.win_loss_ratio.toFixed(2)}</div>
          </section>
        </>
      )}
    </div>
  )
}
