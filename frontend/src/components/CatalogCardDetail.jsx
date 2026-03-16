import { useEffect, useRef, useState, useCallback } from 'react'
import { useNavigate } from 'react-router-dom'
import { useCurrency } from '../context/CurrencyContext'
import { getCatalogRawSales } from '../api/catalog'
import styles from './CatalogCardDetail.module.css'

export default function CatalogCardDetail({ card, history, loading, isLoggedIn, isOwned, onAdd, onClose }) {
  const { fmtPrice } = useCurrency()
  const navigate = useNavigate()
  const panelRef = useRef(null)
  const [rawSales, setRawSales] = useState(null)
  const [rawLoading, setRawLoading] = useState(false)
  const [rawOffset, setRawOffset] = useState(0)
  const [rawTotal, setRawTotal] = useState(0)
  const PAGE = 50

  const loadRawSales = useCallback((offset = 0) => {
    setRawLoading(true)
    getCatalogRawSales(card.id, offset, PAGE)
      .then(d => {
        setRawSales(prev => offset === 0 ? d.sales : [...(prev || []), ...d.sales])
        setRawTotal(d.total)
        setRawOffset(offset)
      })
      .finally(() => setRawLoading(false))
  }, [card.id])

  // Close on Escape
  useEffect(() => {
    const handler = e => { if (e.key === 'Escape') onClose() }
    window.addEventListener('keydown', handler)
    return () => window.removeEventListener('keydown', handler)
  }, [onClose])

  const trend = card.trend
  const trendEl = !trend || trend === 'no data'
    ? <span className={styles.trendFlat}>—</span>
    : trend === 'up'
      ? <span className={styles.trendUp}>▲ up</span>
      : <span className={styles.trendDown}>▼ down</span>

  const hasPriceHistory = history.length > 0
  const maxVal = hasPriceHistory ? Math.max(...history.map(h => h.fair_value || 0)) : 0

  return (
    <div className={styles.overlay} onClick={onClose}>
      <div className={styles.panel} ref={panelRef} onClick={e => e.stopPropagation()}>
        <div className={styles.header}>
          <div className={styles.headerInfo}>
            <div className={styles.playerName}>{card.player_name}</div>
            <div className={styles.cardMeta}>
              {card.year} · {card.set_name}
              {card.card_number ? ` · #${card.card_number}` : ''}
              {card.variant && card.variant !== 'Base' ? ` · ${card.variant}` : ''}
            </div>
            <div className={styles.badges}>
              {card.is_rookie && <span className={styles.rcBadge}>RC</span>}
              {card.scrape_tier && card.scrape_tier !== 'base' && (
                <span className={`${styles.tierBadge} ${styles['tier_' + card.scrape_tier]}`}>
                  {card.scrape_tier.charAt(0).toUpperCase() + card.scrape_tier.slice(1)}
                </span>
              )}
              <span className={styles.sportBadge}>{card.sport}</span>
            </div>
          </div>
          <button className={styles.closeBtn} onClick={onClose}>✕</button>
        </div>

        {/* Price summary */}
        <div className={styles.priceRow}>
          <div className={styles.priceStat}>
            <span className={styles.priceLabel}>Fair Value</span>
            <span className={styles.priceValue}>
              {card.fair_value != null ? fmtPrice(card.fair_value) : '—'}
            </span>
          </div>
          <div className={styles.priceStat}>
            <span className={styles.priceLabel}>Trend</span>
            <span className={styles.priceValue}>{trendEl}</span>
          </div>
          <div className={styles.priceStat}>
            <span className={styles.priceLabel}>Confidence</span>
            <span className={styles.priceValue}>{card.confidence || '—'}</span>
          </div>
          <div className={styles.priceStat}>
            <span className={styles.priceLabel}>Sales</span>
            <span className={styles.priceValue}>{card.num_sales ?? '—'}</span>
          </div>
        </div>

        {/* Price history mini-chart */}
        {loading ? (
          <div className={styles.chartPlaceholder}>Loading history…</div>
        ) : hasPriceHistory ? (
          <div className={styles.chartSection}>
            <div className={styles.chartLabel}>Price History ({history.length} data points)</div>
            <div className={styles.sparkline}>
              <svg viewBox={`0 0 ${history.length * 20} 60`} preserveAspectRatio="none" className={styles.sparkSvg}>
                <polyline
                  fill="none"
                  stroke="var(--accent)"
                  strokeWidth="2"
                  points={history.map((h, i) => {
                    const x = i * 20 + 10
                    const y = maxVal > 0 ? 58 - ((h.fair_value || 0) / maxVal) * 52 : 30
                    return `${x},${y}`
                  }).join(' ')}
                />
                {history.map((h, i) => {
                  const x = i * 20 + 10
                  const y = maxVal > 0 ? 58 - ((h.fair_value || 0) / maxVal) * 52 : 30
                  return <circle key={i} cx={x} cy={y} r="2.5" fill="var(--accent)" opacity="0.7" />
                })}
              </svg>
            </div>
            <div className={styles.chartRange}>
              <span>{history[0]?.scraped_at?.slice(0, 10)}</span>
              <span>{history[history.length - 1]?.scraped_at?.slice(0, 10)}</span>
            </div>

            {/* Last 5 snapshots table */}
            <table className={styles.historyTable}>
              <thead>
                <tr>
                  <th>Date</th>
                  <th>Fair Value</th>
                  <th>Range</th>
                  <th>Sales</th>
                </tr>
              </thead>
              <tbody>
                {[...history].reverse().slice(0, 5).map((h, i) => (
                  <tr key={i}>
                    <td>{h.scraped_at?.slice(0, 10)}</td>
                    <td className={styles.historyVal}>{h.fair_value != null ? fmtPrice(h.fair_value) : '—'}</td>
                    <td className={styles.historyRange}>
                      {h.min_price != null && h.max_price != null
                        ? `${fmtPrice(h.min_price)} – ${fmtPrice(h.max_price)}`
                        : '—'}
                    </td>
                    <td>{h.num_sales ?? '—'}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        ) : (
          <div className={styles.chartPlaceholder}>No price history yet</div>
        )}

        {/* Individual sale history */}
        <div className={styles.salesSection}>
          <div className={styles.salesHeader}>
            <span className={styles.salesTitle}>Sale History</span>
            {rawSales === null && (
              <button className={styles.loadSalesBtn} onClick={() => loadRawSales(0)} disabled={rawLoading}>
                {rawLoading ? 'Loading…' : 'Load'}
              </button>
            )}
            {rawSales !== null && (
              <span className={styles.salesTotalPill}>{rawTotal.toLocaleString()} sales stored</span>
            )}
          </div>

          {rawSales !== null && rawSales.length === 0 && (
            <div className={styles.salesEmpty}>No sales data yet — backfill pending</div>
          )}

          {rawSales !== null && rawSales.length > 0 && (
            <>
              <table className={styles.salesTable}>
                <thead>
                  <tr>
                    <th>Date</th>
                    <th className={styles.saleRight}>Price</th>
                    <th>Listing Title</th>
                  </tr>
                </thead>
                <tbody>
                  {rawSales.map((s, i) => (
                    <tr key={i} className={s.exclusive ? styles.saleExclusive : ''}>
                      <td className={styles.saleDate}>
                        {s.sold_date || '—'}
                        {s.exclusive && <span className={styles.exclusiveDot} title="eBay no longer shows this sale" />}
                      </td>
                      <td className={`${styles.salePrice} ${styles.saleRight}`}>{fmtPrice(s.price_val)}</td>
                      <td className={styles.saleTitle}>{s.title}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
              {rawSales.length < rawTotal && (
                <button className={styles.loadMoreBtn} onClick={() => loadRawSales(rawOffset + PAGE)} disabled={rawLoading}>
                  {rawLoading ? 'Loading…' : `Load more (${rawTotal - rawSales.length} remaining)`}
                </button>
              )}
            </>
          )}
        </div>

        {/* Action */}
        <div className={styles.actions}>
          {isLoggedIn ? (
            isOwned
              ? <span className={styles.ownedBadge}>✓ In your collection</span>
              : <button className={styles.addBtn} onClick={onAdd}>+ Add to Collection</button>
          ) : (
            <button className={styles.signInBtn} onClick={() => navigate('/login')}>
              Sign in to add to your collection
            </button>
          )}
        </div>
      </div>
    </div>
  )
}
