import { useState, useEffect } from 'react'
import { useNavigate } from 'react-router-dom'
import { getTrending } from '../api/catalog'
import styles from './Trending.module.css'

const SPORTS = ['NHL', 'NBA', 'NFL', 'MLB']

function fmt(val) {
  if (val == null) return '—'
  return '$' + Number(val).toLocaleString('en-US', { maximumFractionDigits: 0 })
}

export default function Trending() {
  const navigate = useNavigate()
  const [sport,   setSport]   = useState('')
  const [cards,   setCards]   = useState([])
  const [loading, setLoading] = useState(true)
  const [error,   setError]   = useState(null)

  useEffect(() => {
    setLoading(true)
    setError(null)
    getTrending(sport || null, 24)
      .then(d => setCards(d.cards ?? []))
      .catch(e => setError(e?.message || 'Failed to load'))
      .finally(() => setLoading(false))
  }, [sport])

  return (
    <div className={styles.page}>
      <div className={styles.header}>
        <div className={styles.titleRow}>
          <h1 className={styles.title}>Trending</h1>
          <span className={styles.sub}>Biggest price gains in the last 7 days</span>
        </div>
        <div className={styles.sportTabs}>
          <button className={`${styles.tab} ${sport === '' ? styles.active : ''}`} onClick={() => setSport('')}>All</button>
          {SPORTS.map(s => (
            <button key={s} className={`${styles.tab} ${sport === s ? styles.active : ''}`} onClick={() => setSport(s)}>{s}</button>
          ))}
        </div>
      </div>

      {loading && <div className={styles.status}><span className={styles.spinner} /> Loading…</div>}
      {error   && <div className={styles.error}>{error}</div>}

      {!loading && !error && cards.length === 0 && (
        <div className={styles.empty}>No trending data yet — check back after the next price scrape.</div>
      )}

      {!loading && !error && cards.length > 0 && (
        <div className={styles.grid}>
          {cards.map((card, i) => (
            <button key={card.id} className={styles.card} onClick={() => navigate(`/catalog/${card.id}`)}>
              <div className={styles.rank}>#{i + 1}</div>
              <div className={styles.info}>
                <div className={styles.player}>
                  {card.player_name}
                  {card.is_rookie && <span className={styles.rc}>RC</span>}
                </div>
                <div className={styles.meta}>
                  {card.year} · {card.set_name}
                  {card.variant ? ` · ${card.variant}` : ''}
                </div>
              </div>
              <div className={styles.right}>
                <div className={styles.pct}>
                  {card.pct_change != null ? `+${card.pct_change.toFixed(1)}%` : '—'}
                </div>
                <div className={styles.price}>{fmt(card.fair_value)}</div>
                <div className={styles.sales}>{card.cnt_7d} sales / 7d</div>
              </div>
              <span className={styles.sport}>{card.sport}</span>
            </button>
          ))}
        </div>
      )}
    </div>
  )
}
