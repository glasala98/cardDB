import { useState, useEffect } from 'react'
import { useNavigate } from 'react-router-dom'
import { getNewReleases, getSealedProducts } from '../api/catalog'
import { useCurrency } from '../context/CurrencyContext'
import styles from './Releases.module.css'
import pageStyles from './Page.module.css'

const SPORTS = ['NHL', 'NBA', 'NFL', 'MLB']

// Only show RC badge when the variant name confirms it's a rookie-type card.
// Prevents veteran players with wrong is_rookie flags showing false RC badges.
const RC_KEYWORDS = ['young gun', 'rookie', ' rc', 'young stars', 'debut', 'first']
const isActualRC = (card) =>
  card.is_rookie && RC_KEYWORDS.some(k => (card.variant || '').toLowerCase().includes(k))
const SEASON_OPTIONS = [
  { label: 'Current Season', value: 1 },
  { label: 'Last 2 Seasons', value: 2 },
  { label: 'Last 3 Seasons', value: 3 },
]

const SPORT_COLORS = {
  NHL: { bg: 'rgba(74,158,255,0.12)', text: '#4a9eff', border: 'rgba(74,158,255,0.3)' },
  NBA: { bg: 'rgba(255,107,53,0.12)',  text: '#ff6b35', border: 'rgba(255,107,53,0.3)' },
  NFL: { bg: 'rgba(61,186,94,0.12)',   text: '#3dba5e', border: 'rgba(61,186,94,0.3)' },
  MLB: { bg: 'rgba(224,85,85,0.12)',   color: '#e05555', border: 'rgba(224,85,85,0.3)' },
}


export default function Releases() {
  const { fmtPrice } = useCurrency()
  const navigate = useNavigate()

  const [sets,          setSets]          = useState([])
  const [sealedLookup,  setSealedLookup]  = useState({})
  const [loading,       setLoading]       = useState(false)
  const [error,         setError]         = useState(null)
  const [sport,         setSport]         = useState('')
  const [seasons,       setSeasons]       = useState(2)

  useEffect(() => {
    setLoading(true)
    setError(null)
    const releasesParams = { seasons }
    if (sport) releasesParams.sport = sport
    const sealedParams = sport ? { sport } : {}

    Promise.all([getNewReleases(releasesParams), getSealedProducts(sealedParams)])
      .then(([relData, sealedData]) => {
        setSets(relData.sets || [])
        // Build lookup: "sport|year|set_name" -> [product, ...]
        const lookup = {}
        for (const p of sealedData.products || []) {
          const key = `${p.sport}|${p.year}|${p.set_name}`
          if (!lookup[key]) lookup[key] = []
          lookup[key].push(p)
        }
        setSealedLookup(lookup)
      })
      .catch(e => setError(e.message))
      .finally(() => setLoading(false))
  }, [sport, seasons])

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

      {/* Season filter */}
      <div className={styles.toolbar}>
        {SEASON_OPTIONS.map(opt => (
          <button
            key={opt.value}
            className={`${styles.dayBtn} ${seasons === opt.value ? styles.dayBtnActive : ''}`}
            onClick={() => setSeasons(opt.value)}
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
        <div className={pageStyles.status}>No sets found for the selected season range.</div>
      ) : (
        <div className={styles.grid}>
          {sets.map((s, i) => {
            const sportColor = SPORT_COLORS[s.sport] || {}
            const coveragePercent = s.card_count > 0
              ? Math.round((s.priced_count / s.card_count) * 100)
              : 0

            // Sealed product data for this set
            const setKey = `${s.sport}|${s.year}|${s.set_name}`
            const boxProducts = sealedLookup[setKey] || []
            const hobbyBox  = boxProducts.find(p => p.product_type === 'Hobby Box' || p.product_type === 'Hobby Jumbo Box')
            const blasterBox = boxProducts.find(p => p.product_type === 'Blaster Box')
            // Crude EV: cards_per_box × avg card value in the set
            const cardsPerBox = hobbyBox?.cards_per_pack && hobbyBox?.packs_per_box
              ? hobbyBox.cards_per_pack * hobbyBox.packs_per_box
              : null
            const evHobby = cardsPerBox && s.avg_value
              ? Math.round(cardsPerBox * s.avg_value * 100) / 100
              : null
            const evDiffPct = evHobby != null && hobbyBox?.msrp
              ? ((evHobby - hobbyBox.msrp) / hobbyBox.msrp * 100).toFixed(1)
              : null

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
                  <div className={styles.headerRight}>
                    {s.flagship_count > 0 && (
                      <span className={styles.flagshipBadge} title={`${s.staple_count} staple cards`}>
                        Flagship
                      </span>
                    )}
                    {s.momentum_pct != null && (
                      <span className={`${styles.momentumBadge} ${s.momentum_pct >= 0 ? styles.momentumUp : styles.momentumDown}`}>
                        {s.momentum_pct >= 0 ? '+' : ''}{s.momentum_pct}%
                      </span>
                    )}
                  </div>
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
                  {s.total_sales > 0 && (
                    <div className={styles.stat}>
                      <span className={styles.statVal}>{s.total_sales.toLocaleString()}</span>
                      <span className={styles.statLabel}>sales</span>
                    </div>
                  )}
                  <div className={styles.stat}>
                    <span className={styles.statVal}>{coveragePercent}%</span>
                    <span className={styles.statLabel}>priced</span>
                  </div>
                </div>

                {/* Box pricing + EV */}
                {boxProducts.length > 0 && (
                  <div className={styles.boxPricing}>
                    <div className={styles.boxPricingRow}>
                      {hobbyBox?.msrp != null && (
                        <div className={styles.boxItem}>
                          <span className={styles.boxLabel}>Hobby MSRP</span>
                          <span className={styles.boxPrice}>{fmtPrice(hobbyBox.msrp)}</span>
                        </div>
                      )}
                      {blasterBox?.msrp != null && (
                        <div className={styles.boxItem}>
                          <span className={styles.boxLabel}>Blaster MSRP</span>
                          <span className={styles.boxPrice}>{fmtPrice(blasterBox.msrp)}</span>
                        </div>
                      )}
                      {evHobby != null && (
                        <div className={styles.boxItem}>
                          <span className={styles.boxLabel}>EV est.</span>
                          <span className={`${styles.boxPrice} ${evHobby >= (hobbyBox?.msrp ?? Infinity) ? styles.evPositive : styles.evNegative}`}>
                            {fmtPrice(evHobby)}
                          </span>
                        </div>
                      )}
                    </div>
                    {evDiffPct != null && (
                      <div className={styles.evNote}>
                        <span className={Number(evDiffPct) >= 0 ? styles.evPositive : styles.evNegative}>
                          {Number(evDiffPct) >= 0 ? '+' : ''}{evDiffPct}% vs MSRP
                        </span>
                        <span className={styles.evDisclaimer}> · avg card × cards/box</span>
                      </div>
                    )}
                  </div>
                )}

                {/* Top cards */}
                {s.top_cards.length > 0 && (
                  <div className={styles.topCards}>
                    {s.top_cards.map((c, ci) => (
                      <div key={ci} className={styles.topCard}>
                        <span className={styles.topCardRank}>#{ci + 1}</span>
                        <span className={styles.topCardName}>{c.player_name}</span>
                        {isActualRC(c) && <span className={styles.rcBadge}>RC</span>}
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
