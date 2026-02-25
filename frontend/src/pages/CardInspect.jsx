import { useState, useEffect } from 'react'
import { useParams, Link } from 'react-router-dom'
import PriceChart from '../components/PriceChart'
import ConfidenceBadge from '../components/ConfidenceBadge'
import TrendBadge from '../components/TrendBadge'
import { getCardDetail, scrapeCard } from '../api/cards'
import { useCurrency } from '../context/CurrencyContext'
import pageStyles from './Page.module.css'
import styles from './CardInspect.module.css'

export default function CardInspect() {
  const { cardName } = useParams()
  const name = decodeURIComponent(cardName)

  const [data,     setData]     = useState(null)
  const [loading,  setLoading]  = useState(true)
  const [error,    setError]    = useState(null)
  const [scraping, setScraping] = useState(false)
  const [toast,    setToast]    = useState(null)

  const load = () => {
    setLoading(true)
    getCardDetail(name)
      .then(setData)
      .catch(e => setError(e.message))
      .finally(() => setLoading(false))
  }
  useEffect(load, [name])

  const showToast = (msg, type = 'success') => {
    setToast({ msg, type })
    setTimeout(() => setToast(null), 3500)
  }

  const handleScrape = async () => {
    setScraping(true)
    try {
      await scrapeCard(name)
      showToast('Scrape queued — refresh in ~30s to see updated price')
    } catch (e) {
      showToast(e.message, 'error')
    } finally {
      setScraping(false)
    }
  }

  if (loading) return <p className={pageStyles.status}>Loading…</p>
  if (error)   return <p className={pageStyles.error}>Error: {error}</p>
  if (!data)   return <p className={pageStyles.status}>Card not found.</p>

  const { card, price_history, raw_sales, confidence, search_url, image_url } = data

  const { fmtPrice } = useCurrency()
  const gain     = (card.fair_value ?? 0) - (card.cost_basis ?? 0)
  const hasValue = card.fair_value != null && card.fair_value > 0
  const hasCost  = card.cost_basis != null && card.cost_basis > 0
  const fmt      = v => fmtPrice(v)

  return (
    <div className={pageStyles.page}>

      {toast && <div className={`${styles.toast} ${styles[toast.type]}`}>{toast.msg}</div>}

      <Link to="/ledger" className={styles.back}>← Back to Ledger</Link>

      <div className={styles.cardHeader}>
        {image_url && (
          <img
            src={image_url}
            alt={name}
            className={styles.cardImage}
            onError={e => { e.currentTarget.style.display = 'none' }}
          />
        )}
        <div className={styles.titleRow}>
          <h1 className={styles.cardTitle}>{name}</h1>
          <div className={styles.headerActions}>
            <ConfidenceBadge confidence={confidence} />
            <button
              className={styles.scrapeBtn}
              onClick={handleScrape}
              disabled={scraping}
            >
              {scraping ? 'Queuing…' : '⟳ Rescrape'}
            </button>
            {search_url && (
              <a
                href={search_url}
                target="_blank"
                rel="noopener noreferrer"
                className={styles.ebayLink}
              >
                View on eBay ↗
              </a>
            )}
          </div>
        </div>
        {card.last_scraped && (
          <p className={styles.lastScraped}>Last scraped: {card.last_scraped}</p>
        )}
      </div>

      {/* ── Metrics ── */}
      <div className={styles.metrics}>
        <MetricCard label="Fair Value" value={fmt(card.fair_value)} large />
        <MetricCard label="Cost Basis" value={fmt(card.cost_basis)} />
        {hasCost && hasValue && (
          <MetricCard
            label="Gain / Loss"
            value={`${gain >= 0 ? '+' : ''}${fmt(gain)}`}
            color={gain >= 0 ? 'success' : 'danger'}
          />
        )}
        <MetricCard label="Trend"  value={<TrendBadge trend={card.trend} />} />
        <MetricCard label="Sales"  value={card.num_sales || '—'} />
        <MetricCard label="Median" value={fmt(card.median_all)} />
        <MetricCard label="Min"    value={fmt(card.min)} />
        <MetricCard label="Max"    value={fmt(card.max)} />
        {card.purchase_date && (
          <MetricCard label="Purchased" value={card.purchase_date} />
        )}
      </div>

      {card.top3 && (
        <p className={styles.top3}>
          <span className={styles.top3Label}>Top 3 recent:</span> {card.top3}
        </p>
      )}

      {/* ── Price History Chart ── */}
      <div className={styles.section}>
        <PriceChart data={price_history || []} title="Price History" />
      </div>

      {/* ── Sales Table ── */}
      <div className={styles.section}>
        <div className={styles.sectionHeader}>
          <h2 className={styles.sectionTitle}>Sales History</h2>
          <span className={styles.sectionCount}>{raw_sales.length} records</span>
        </div>

        {raw_sales.length === 0 ? (
          <p className={styles.empty}>No direct sales on record yet.</p>
        ) : (
          <div className={styles.salesWrap}>
            <table className={styles.salesTable}>
              <thead>
                <tr>
                  <th className={styles.th}>Date</th>
                  <th className={styles.th}>Price</th>
                  <th className={styles.th}>Title</th>
                </tr>
              </thead>
              <tbody>
                {raw_sales.map((s, i) => (
                  <tr key={i} className={styles.salesRow}>
                    <td className={`${styles.td} ${styles.dateCell}`}>{s.sold_date || '—'}</td>
                    <td className={`${styles.td} ${styles.priceCell}`}>
                      {s.price != null ? fmtPrice(s.price) : '—'}
                    </td>
                    <td className={`${styles.td} ${styles.titleCell}`}>
                      {s.listing_url ? (
                        <a href={s.listing_url} target="_blank" rel="noopener noreferrer" className={styles.saleLink}>
                          {s.title}
                        </a>
                      ) : s.title}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>
    </div>
  )
}

function MetricCard({ label, value, large, color }) {
  const colorClass = color === 'success' ? styles.success : color === 'danger' ? styles.danger : ''
  return (
    <div className={styles.metric}>
      <span className={styles.metricLabel}>{label}</span>
      <span className={`${styles.metricValue} ${large ? styles.large : ''} ${colorClass}`}>
        {value}
      </span>
    </div>
  )
}
