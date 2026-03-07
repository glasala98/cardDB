import { useState, useEffect } from 'react'
import { useNavigate } from 'react-router-dom'
import { getNewReleases } from '../api/catalog'
import { useCurrency } from '../context/CurrencyContext'
import styles from './Releases.module.css'
import pageStyles from './Page.module.css'

const SPORTS = ['NHL', 'NBA', 'NFL', 'MLB']
const DAY_OPTIONS = [
  { label: 'Last 30 days', value: 30 },
  { label: 'Last 60 days', value: 60 },
  { label: 'Last 90 days', value: 90 },
]

const SPORT_COLORS = {
  NHL: { bg: 'rgba(74,158,255,0.12)', text: '#4a9eff', border: 'rgba(74,158,255,0.3)' },
  NBA: { bg: 'rgba(255,107,53,0.12)',  text: '#ff6b35', border: 'rgba(255,107,53,0.3)' },
  NFL: { bg: 'rgba(61,186,94,0.12)',   text: '#3dba5e', border: 'rgba(61,186,94,0.3)' },
  MLB: { bg: 'rgba(224,85,85,0.12)',   color: '#e05555', border: 'rgba(224,85,85,0.3)' },
}

function daysAgo(isoStr) {
  if (!isoStr) return null
  const diff = Date.now() - new Date(isoStr).getTime()
  const d = Math.floor(diff / 86400000)
  if (d === 0) return 'Today'
  if (d === 1) return '1 day ago'
  return `${d} days ago`
}

export default function Releases() {
  const { fmtPrice } = useCurrency()
  const navigate = useNavigate()

  const [sets,    setSets]    = useState([])
  const [loading, setLoading] = useState(false)
  const [error,   setError]   = useState(null)
  const [sport,   setSport]   = useState('')
  const [days,    setDays]    = useState(60)

  useEffect(() => {
    setLoading(true)
    setError(null)
    const params = { days }
    if (sport) params.sport = sport
    getNewReleases(params)
      .then(data => setSets(data.sets || []))
      .catch(e => setError(e.message))
      .finally(() => setLoading(false))
  }, [sport, days])

  const goToCatalog = (s, e) => {
    e.stopPropagation()
    navigate(`/catalog?sport=${s.sport}&year=${encodeURIComponent(s.year)}&set_name=${encodeURIComponent(s.set_name)}`)
  }

  return (
    <div className={pageStyles.page}>
      <div className={pageStyles.header}>
        <h1 className={pageStyles.title}>New Releases</h1>
        {!loading && <span className={pageStyles.count}>{sets.length} sets</span>}
      </div>

      {/* Sport tabs */}
      <div className={styles.sportTabs}>
        {['', ...SPORTS].map(s => (
          <button
            key={s || 'all'}
            className={`${styles.tab} ${sport === s ? styles.tabActive : ''}`}
            onClick={() => setSport(s)}
          >
            {s || 'All Sports'}
          </button>
        ))}
      </div>

      {/* Days filter */}
      <div className={styles.toolbar}>
        {DAY_OPTIONS.map(opt => (
          <button
            key={opt.value}
            className={`${styles.dayBtn} ${days === opt.value ? styles.dayBtnActive : ''}`}
            onClick={() => setDays(opt.value)}
          >
            {opt.label}
          </button>
        ))}
      </div>

      {error && <div className={pageStyles.error}>{error}</div>}

      {loading ? (
        <div className={styles.grid}>
          {Array.from({ length: 9 }).map((_, i) => (
            <div key={i} className={`${styles.setCard} ${styles.skeletonCard}`}>
              <div className={styles.skeletonBlock} style={{ width: '60%', height: 14 }} />
              <div className={styles.skeletonBlock} style={{ width: '40%', height: 11, marginTop: 6 }} />
              <div className={styles.skeletonBlock} style={{ width: '80%', height: 22, marginTop: 12 }} />
              <div style={{ marginTop: 12, display: 'flex', flexDirection: 'column', gap: 6 }}>
                {[1,2,3].map(j => (
                  <div key={j} className={styles.skeletonBlock} style={{ height: 11 }} />
                ))}
              </div>
            </div>
          ))}
        </div>
      ) : sets.length === 0 ? (
        <div className={pageStyles.status}>No new sets found in the last {days} days.</div>
      ) : (
        <div className={styles.grid}>
          {sets.map((s, i) => {
            const sportColor = SPORT_COLORS[s.sport] || {}
            const coveragePercent = s.card_count > 0
              ? Math.round((s.priced_count / s.card_count) * 100)
              : 0

            return (
              <div key={i} className={styles.setCard} onClick={(e) => goToCatalog(s, e)}>
                {/* Header */}
                <div className={styles.setHeader}>
                  <span
                    className={styles.sportBadge}
                    style={{ background: sportColor.bg, color: sportColor.text, borderColor: sportColor.border }}
                  >
                    {s.sport}
                  </span>
                  <span className={styles.indexedAt}>{daysAgo(s.indexed_at)}</span>
                </div>

                {/* Set name + year */}
                <div className={styles.setName}>{s.set_name}</div>
                <div className={styles.setMeta}>
                  {s.year}{s.brand && s.brand !== s.set_name ? ` · ${s.brand}` : ''}
                </div>

                {/* Stats row */}
                <div className={styles.statsRow}>
                  <div className={styles.stat}>
                    <span className={styles.statVal}>{s.card_count.toLocaleString()}</span>
                    <span className={styles.statLabel}>cards</span>
                  </div>
                  {s.top_value != null && (
                    <div className={styles.stat}>
                      <span className={`${styles.statVal} ${styles.statHighlight}`}>{fmtPrice(s.top_value)}</span>
                      <span className={styles.statLabel}>top card</span>
                    </div>
                  )}
                  {s.avg_value != null && (
                    <div className={styles.stat}>
                      <span className={styles.statVal}>{fmtPrice(s.avg_value)}</span>
                      <span className={styles.statLabel}>avg</span>
                    </div>
                  )}
                  <div className={styles.stat}>
                    <span className={styles.statVal}>{coveragePercent}%</span>
                    <span className={styles.statLabel}>priced</span>
                  </div>
                </div>

                {/* Top cards */}
                {s.top_cards.length > 0 && (
                  <div className={styles.topCards}>
                    {s.top_cards.map((c, ci) => (
                      <div key={ci} className={styles.topCard}>
                        <span className={styles.topCardRank}>#{ci + 1}</span>
                        <span className={styles.topCardName}>{c.player_name}</span>
                        {c.is_rookie && <span className={styles.rcBadge}>RC</span>}
                        {c.fair_value != null && (
                          <span className={styles.topCardPrice}>{fmtPrice(c.fair_value)}</span>
                        )}
                      </div>
                    ))}
                  </div>
                )}

                <div className={styles.viewLink}>View in Catalog →</div>
              </div>
            )
          })}
        </div>
      )}
    </div>
  )
}
