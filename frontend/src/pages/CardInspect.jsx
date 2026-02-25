import { useState, useEffect } from 'react'
import { useParams, Link } from 'react-router-dom'
import PriceChart from '../components/PriceChart'
import ConfidenceBadge from '../components/ConfidenceBadge'
import TrendBadge from '../components/TrendBadge'
import CardTable from '../components/CardTable'
import { getCardDetail } from '../api/cards'
import styles from './Page.module.css'
import cardStyles from './CardInspect.module.css'

const SALES_COLS = [
  { key: 'sold_date', label: 'Date' },
  { key: 'title',     label: 'Title' },
  { key: 'price',     label: 'Price', render: v => v ? `$${Number(v).toFixed(2)}` : '—' },
]

export default function CardInspect() {
  const { cardName } = useParams()
  const name = decodeURIComponent(cardName)
  const [data, setData] = useState(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(null)

  useEffect(() => {
    getCardDetail(name)
      .then(setData)
      .catch(e => setError(e.message))
      .finally(() => setLoading(false))
  }, [name])

  if (loading) return <p className={styles.status}>Loading...</p>
  if (error)   return <p className={styles.error}>Error: {error}</p>
  if (!data)   return <p className={styles.status}>Card not found.</p>

  const { card, price_history, raw_sales, confidence } = data

  return (
    <div className={styles.page}>
      <div className={styles.header}>
        <Link to="/ledger" className={cardStyles.back}>← Back to Ledger</Link>
        <h1 className={styles.title}>{name}</h1>
        <ConfidenceBadge confidence={confidence} />
      </div>

      <div className={cardStyles.metrics}>
        <div className={cardStyles.metric}>
          <span className={cardStyles.metricLabel}>Fair Value</span>
          <span className={cardStyles.metricValue}>
            {card?.fair_value ? `$${Number(card.fair_value).toFixed(2)}` : '—'}
          </span>
        </div>
        <div className={cardStyles.metric}>
          <span className={cardStyles.metricLabel}>Cost Basis</span>
          <span className={cardStyles.metricValue}>
            {card?.cost_basis ? `$${Number(card.cost_basis).toFixed(2)}` : '—'}
          </span>
        </div>
        <div className={cardStyles.metric}>
          <span className={cardStyles.metricLabel}>Trend</span>
          <TrendBadge trend={card?.trend} />
        </div>
        <div className={cardStyles.metric}>
          <span className={cardStyles.metricLabel}>Sales (90d)</span>
          <span className={cardStyles.metricValue}>{card?.num_sales ?? '—'}</span>
        </div>
      </div>

      <PriceChart
        data={price_history || []}
        title="Price History"
      />

      <div className={cardStyles.section}>
        <h2 className={cardStyles.sectionTitle}>Recent Sales</h2>
        <CardTable
          columns={SALES_COLS}
          rows={raw_sales || []}
        />
      </div>
    </div>
  )
}
