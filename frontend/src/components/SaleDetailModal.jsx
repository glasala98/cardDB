import { useEffect, useState, useRef } from 'react'
import SourceBadge from './SourceBadge'
import GradeBadge from './GradeBadge'
import styles from './SaleDetailModal.module.css'
import client from '../api/client'

function fmt(v) {
  if (v == null) return '—'
  return '$' + Number(v).toLocaleString('en-US', { minimumFractionDigits: 0, maximumFractionDigits: 0 })
}

function fmtDate(d) {
  if (!d) return ''
  return new Date(d).toLocaleDateString('en-US', { month: 'short', day: 'numeric', year: 'numeric' })
}

// Tiny inline sparkline using canvas
function Sparkline({ points, width = 320, height = 70 }) {
  const ref = useRef(null)
  useEffect(() => {
    if (!ref.current || !points?.length) return
    const vals = points.map(p => p.price).filter(Boolean)
    if (!vals.length) return
    const ctx = ref.current.getContext('2d')
    const min = Math.min(...vals)
    const max = Math.max(...vals)
    const range = max - min || 1
    const W = width, H = height, pad = 6

    ctx.clearRect(0, 0, W, H)
    const x = i => pad + (i / (vals.length - 1 || 1)) * (W - 2 * pad)
    const y = v => H - pad - ((v - min) / range) * (H - 2 * pad)

    // gradient fill
    const grad = ctx.createLinearGradient(0, 0, 0, H)
    grad.addColorStop(0, 'rgba(108,99,255,0.3)')
    grad.addColorStop(1, 'rgba(108,99,255,0.02)')
    ctx.beginPath()
    ctx.moveTo(x(0), y(vals[0]))
    for (let i = 1; i < vals.length; i++) ctx.lineTo(x(i), y(vals[i]))
    ctx.lineTo(x(vals.length - 1), H)
    ctx.lineTo(x(0), H)
    ctx.closePath()
    ctx.fillStyle = grad
    ctx.fill()

    // line
    ctx.beginPath()
    ctx.strokeStyle = '#6c63ff'
    ctx.lineWidth = 2
    ctx.lineJoin = 'round'
    ctx.moveTo(x(0), y(vals[0]))
    for (let i = 1; i < vals.length; i++) ctx.lineTo(x(i), y(vals[i]))
    ctx.stroke()

    // dots
    vals.forEach((v, i) => {
      ctx.beginPath()
      ctx.arc(x(i), y(v), 3, 0, Math.PI * 2)
      ctx.fillStyle = '#6c63ff'
      ctx.fill()
    })
  }, [points, width, height])

  if (!points?.length) return null
  return <canvas ref={ref} width={width} height={height} className={styles.sparkCanvas} />
}

export default function SaleDetailModal({ sale, onClose }) {
  const [history, setHistory] = useState(null)
  const overlayRef = useRef(null)

  useEffect(() => {
    if (!sale?.card_catalog_id) return
    client.get(`/catalog/${sale.card_catalog_id}/history`).then(data => {
      setHistory(data)
    }).catch(() => setHistory([]))
  }, [sale?.card_catalog_id])

  useEffect(() => {
    function onKey(e) { if (e.key === 'Escape') onClose() }
    document.addEventListener('keydown', onKey)
    return () => document.removeEventListener('keydown', onKey)
  }, [onClose])

  if (!sale) return null

  const hasPremium = sale.hammer_price != null && sale.buyer_premium_pct != null

  // Build sparkline points from history (price over time)
  const sparkPoints = (history ?? [])
    .filter(h => h.price_val && h.sold_date)
    .sort((a, b) => new Date(a.sold_date) - new Date(b.sold_date))
    .slice(-30)
    .map(h => ({ price: h.price_val, date: h.sold_date }))

  const allPrices = sparkPoints.map(p => p.price)
  const avgPrice  = allPrices.length ? (allPrices.reduce((a, b) => a + b, 0) / allPrices.length) : null
  const minPrice  = allPrices.length ? Math.min(...allPrices) : null
  const maxPrice  = allPrices.length ? Math.max(...allPrices) : null

  return (
    <div className={styles.overlay} ref={overlayRef} onClick={e => { if (e.target === overlayRef.current) onClose() }}>
      <div className={styles.modal}>
        <button className={styles.close} onClick={onClose}>×</button>

        <div className={styles.header}>
          <div className={styles.badges}>
            <SourceBadge source={sale.source} size="md" />
            {sale.grade && <GradeBadge grade={sale.grade} />}
            {sale.is_rookie && <span className={styles.rcBadge}>RC</span>}
          </div>
          <div className={styles.player}>{sale.player_name ?? sale.title}</div>
          {sale.year && sale.set_name && (
            <div className={styles.cardMeta}>{sale.year} {sale.set_name}{sale.variant ? ` — ${sale.variant}` : ''}</div>
          )}
        </div>

        <div className={styles.priceRow}>
          <div className={styles.mainPrice}>
            <span className={styles.priceLabel}>Sale Price</span>
            <span className={styles.priceVal}>{fmt(sale.price_val)}</span>
          </div>
          {hasPremium && (
            <div className={styles.premiumBlock}>
              <span className={styles.priceLabel}>Hammer</span>
              <span className={styles.priceVal}>{fmt(sale.hammer_price)}</span>
              <span className={styles.premiumNote}>+{sale.buyer_premium_pct}% premium</span>
            </div>
          )}
          {sale.serial_number && sale.print_run && (
            <div className={styles.serialBlock}>
              <span className={styles.priceLabel}>Print Run</span>
              <span className={styles.serialVal}>#{sale.serial_number}/{sale.print_run}</span>
            </div>
          )}
        </div>

        <div className={styles.meta2}>
          <span>Sold {fmtDate(sale.sold_date)}</span>
          {sale.sport && <span>{sale.sport}</span>}
        </div>

        {sale.title && (
          <div className={styles.titleFull}>"{sale.title}"</div>
        )}

        {sale.lot_url && (
          <a href={sale.lot_url} target="_blank" rel="noopener noreferrer" className={styles.viewLink}>
            View original listing →
          </a>
        )}

        <div className={styles.historySection}>
          <div className={styles.historyHead}>
            Price History (last 30 sales)
            {history === null && <span className={styles.loadingDot}>…</span>}
          </div>

          {sparkPoints.length > 1 && (
            <>
              <Sparkline points={sparkPoints} width={480} height={90} />
              <div className={styles.statsRow}>
                <div className={styles.stat}><span>Avg</span><strong>{fmt(avgPrice)}</strong></div>
                <div className={styles.stat}><span>Low</span><strong>{fmt(minPrice)}</strong></div>
                <div className={styles.stat}><span>High</span><strong>{fmt(maxPrice)}</strong></div>
                <div className={styles.stat}><span>Sales</span><strong>{allPrices.length}</strong></div>
              </div>
            </>
          )}

          {history !== null && sparkPoints.length <= 1 && (
            <div className={styles.noHistory}>Not enough history to show chart.</div>
          )}
        </div>
      </div>
    </div>
  )
}
