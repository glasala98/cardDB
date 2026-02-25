import { useState, useEffect } from 'react'
import PriceChart from '../components/PriceChart'
import { getPortfolioHistory } from '../api/cards'
import styles from './Page.module.css'
import portfolioStyles from './Portfolio.module.css'

export default function Portfolio() {
  const [history, setHistory] = useState([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(null)

  useEffect(() => {
    getPortfolioHistory()
      .then(data => setHistory(data.history || []))
      .catch(e => setError(e.message))
      .finally(() => setLoading(false))
  }, [])

  const latest = history[history.length - 1]

  return (
    <div className={styles.page}>
      <div className={styles.header}>
        <h1 className={styles.title}>Portfolio</h1>
      </div>

      {loading && <p className={styles.status}>Loading...</p>}
      {error   && <p className={styles.error}>Error: {error}</p>}

      {!loading && !error && (
        <>
          <div className={portfolioStyles.metrics}>
            <div className={portfolioStyles.metric}>
              <span className={portfolioStyles.label}>Total Value</span>
              <span className={portfolioStyles.value}>
                {latest ? `$${Number(latest.total_value).toLocaleString('en-CA', { minimumFractionDigits: 2 })}` : '—'}
              </span>
            </div>
            <div className={portfolioStyles.metric}>
              <span className={portfolioStyles.label}>Cards Tracked</span>
              <span className={portfolioStyles.value}>{latest?.total_cards ?? '—'}</span>
            </div>
            <div className={portfolioStyles.metric}>
              <span className={portfolioStyles.label}>Avg per Card</span>
              <span className={portfolioStyles.value}>
                {latest ? `$${Number(latest.avg_value).toFixed(2)}` : '—'}
              </span>
            </div>
          </div>

          <PriceChart
            data={history.map(h => ({ date: h.date, price: h.total_value }))}
            title="Portfolio Value Over Time"
          />
        </>
      )}
    </div>
  )
}
