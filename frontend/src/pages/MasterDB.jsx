import { useState, useEffect, useMemo } from 'react'
import { ScatterChart, Scatter, XAxis, YAxis, Tooltip, ResponsiveContainer, CartesianGrid,
         BarChart, Bar, Cell, LineChart, Line, Legend } from 'recharts'
import TrendBadge from '../components/TrendBadge'
import { getYoungGuns, getMarketMovers, getNHLStats, getSeasonalTrends } from '../api/masterDb'
import styles from './MasterDB.module.css'
import pageStyles from './Page.module.css'

const PRICE_MODES = [
  { key: 'fair_value',  label: 'Raw' },
  { key: 'psa8_price',  label: 'PSA 8' },
  { key: 'psa9_price',  label: 'PSA 9' },
  { key: 'psa10_price', label: 'PSA 10' },
  { key: 'bgs9_price',  label: 'BGS 9' },
  { key: 'bgs95_price', label: 'BGS 9.5' },
  { key: 'bgs10_price', label: 'BGS 10' },
]

const fmt = v => v ? `$${Number(v).toFixed(2)}` : '—'

export default function MasterDB() {
  const [cards,    setCards]    = useState([])
  const [seasons,  setSeasons]  = useState([])
  const [teams,    setTeams]    = useState([])
  const [movers,   setMovers]   = useState({ gainers: [], losers: [] })
  const [loading,  setLoading]  = useState(true)
  const [error,    setError]    = useState(null)

  // Filters
  const [search,     setSearch]     = useState('')
  const [season,     setSeason]     = useState('')
  const [team,       setTeam]       = useState('')
  const [myCards,    setMyCards]    = useState(false)
  const [priceMode,  setPriceMode]  = useState('fair_value')

  // Sort
  const [sortKey, setSortKey] = useState('fair_value')
  const [sortDir, setSortDir] = useState('desc')

  const [nhlStats,       setNhlStats]       = useState([])
  const [seasonalTrends, setSeasonalTrends] = useState([])

  useEffect(() => {
    Promise.all([getYoungGuns(), getMarketMovers(), getNHLStats(), getSeasonalTrends()])
      .then(([yg, mv, ns, st]) => {
        setCards(yg.cards || [])
        setSeasons(yg.seasons || [])
        setTeams(yg.teams || [])
        setMovers(mv)
        setNhlStats(ns.players || [])
        setSeasonalTrends(st.months || [])
      })
      .catch(e => setError(e.message))
      .finally(() => setLoading(false))
  }, [])

  const filtered = useMemo(() => {
    const s = search.toLowerCase()
    return cards
      .filter(c => {
        if (s && !(
          c.player?.toLowerCase().includes(s) ||
          c.team?.toLowerCase().includes(s) ||
          c.set?.toLowerCase().includes(s) ||
          String(c.season).includes(s) ||
          String(c.card_number).includes(s)
        )) return false
        if (season && String(c.season) !== season) return false
        if (team   && c.team !== team)              return false
        if (myCards && !c.owned)                    return false
        return true
      })
      .sort((a, b) => {
        const av = a[sortKey] ?? -1
        const bv = b[sortKey] ?? -1
        return sortDir === 'desc' ? bv - av : av - bv
      })
  }, [cards, search, season, team, myCards, sortKey, sortDir, priceMode])

  const handleSort = key => {
    if (sortKey === key) setSortDir(d => d === 'asc' ? 'desc' : 'asc')
    else { setSortKey(key); setSortDir('desc') }
  }

  const SortTh = ({ col, label, className }) => (
    <th className={`${styles.th} ${className || ''}`} onClick={() => handleSort(col)}>
      {label}
      {sortKey === col && <span className={styles.arrow}>{sortDir === 'asc' ? ' ↑' : ' ↓'}</span>}
    </th>
  )

  return (
    <div className={pageStyles.page}>

      <div className={pageStyles.header}>
        <h1 className={pageStyles.title}>Young Guns Master DB</h1>
        <span className={pageStyles.count}>{cards.length.toLocaleString()} cards</span>
      </div>

      {/* ── Market Movers Banner ── */}
      {!loading && (movers.gainers.length > 0 || movers.losers.length > 0) && (
        <div className={styles.moversBanner}>
          {[...movers.gainers.slice(0, 3), ...movers.losers.slice(0, 3)].map(m => (
            <div
              key={m.card_name}
              className={`${styles.moverCard} ${m.direction === 'up' ? styles.moverUp : styles.moverDown}`}
            >
              <span className={styles.moverName}>{m.card_name}</span>
              <span className={styles.moverPct}>
                {m.pct_change >= 0 ? '+' : ''}{m.pct_change}%
              </span>
              <span className={styles.moverPrices}>
                {fmt(m.old_price)} → {fmt(m.new_price)}
              </span>
            </div>
          ))}
        </div>
      )}

      {/* ── Price Mode Selector ── */}
      <div className={styles.priceModebar}>
        <span className={styles.priceModeLabel}>Price Mode</span>
        {PRICE_MODES.map(({ key, label }) => (
          <button
            key={key}
            className={`${styles.priceModeBtn} ${priceMode === key ? styles.pmActive : ''}`}
            onClick={() => { setPriceMode(key); setSortKey(key) }}
          >
            {label}
          </button>
        ))}
      </div>

      {/* ── Filters ── */}
      <div className={styles.filters}>
        <input
          className={pageStyles.search}
          placeholder="Search by player, team, season, card #..."
          value={search}
          onChange={e => setSearch(e.target.value)}
        />

        <select className={styles.filterSelect} value={season} onChange={e => setSeason(e.target.value)}>
          <option value="">All Seasons</option>
          {seasons.map(s => <option key={s} value={s}>{s}</option>)}
        </select>

        <select className={styles.filterSelect} value={team} onChange={e => setTeam(e.target.value)}>
          <option value="">All Teams</option>
          {teams.map(t => <option key={t} value={t}>{t}</option>)}
        </select>

        <label className={styles.myCardsToggle}>
          <input
            type="checkbox"
            checked={myCards}
            onChange={e => setMyCards(e.target.checked)}
          />
          My Cards
        </label>

        {(search || season || team || myCards) && (
          <button className={styles.clearBtn} onClick={() => {
            setSearch(''); setSeason(''); setTeam(''); setMyCards(false)
          }}>
            Clear filters
          </button>
        )}
      </div>

      <p className={styles.showing}>
        Showing {filtered.length.toLocaleString()} of {cards.length.toLocaleString()} cards
      </p>

      {loading && <p className={pageStyles.status}>Loading…</p>}
      {error   && <p className={pageStyles.error}>Error: {error}</p>}

      {!loading && !error && (
        <div className={styles.tableWrap}>
          <table className={styles.table}>
            <thead>
              <tr>
                <th className={styles.th}>Season</th>
                <th className={styles.th}>#</th>
                <th className={styles.th}>Player</th>
                <th className={styles.th}>Team</th>
                <SortTh col="fair_value"  label="Raw ($)"    className={priceMode === 'fair_value'  ? styles.activeCol : ''} />
                <SortTh col="num_sales"   label="Sales" />
                <th className={styles.th}>Min ($)</th>
                <th className={styles.th}>Max ($)</th>
                <SortTh col="trend"       label="Trend" />
                <th className={styles.th}>Last Scraped</th>
                <SortTh col="psa10_price" label="PSA 10"  className={priceMode === 'psa10_price' ? styles.activeCol : ''} />
                <SortTh col="psa9_price"  label="PSA 9"   className={priceMode === 'psa9_price'  ? styles.activeCol : ''} />
                <SortTh col="psa8_price"  label="PSA 8"   className={priceMode === 'psa8_price'  ? styles.activeCol : ''} />
                <SortTh col="bgs10_price" label="BGS 10"  className={priceMode === 'bgs10_price' ? styles.activeCol : ''} />
                <SortTh col="bgs95_price" label="BGS 9.5" className={priceMode === 'bgs95_price' ? styles.activeCol : ''} />
                <SortTh col="bgs9_price"  label="BGS 9"   className={priceMode === 'bgs9_price'  ? styles.activeCol : ''} />
              </tr>
            </thead>
            <tbody>
              {filtered.length === 0 && (
                <tr><td colSpan={16} className={styles.empty}>No cards match the current filters.</td></tr>
              )}
              {filtered.map((card, i) => (
                <tr key={`${card.season}-${card.card_number}-${i}`} className={`${styles.tr} ${card.owned ? styles.ownedRow : ''}`}>
                  <td className={styles.td}>{card.season}</td>
                  <td className={styles.td}>{card.card_number}</td>
                  <td className={`${styles.td} ${styles.playerCell}`}>{card.player}</td>
                  <td className={styles.td}>{card.team}</td>
                  <td className={`${styles.td} ${styles.priceCell} ${priceMode === 'fair_value' ? styles.activePriceCol : ''}`}>
                    {fmt(card.fair_value)}
                  </td>
                  <td className={styles.td}>{card.num_sales || '—'}</td>
                  <td className={styles.td}>{fmt(card.min)}</td>
                  <td className={styles.td}>{fmt(card.max)}</td>
                  <td className={styles.td}><TrendBadge trend={card.trend} /></td>
                  <td className={`${styles.td} ${styles.dateCell}`}>{card.last_scraped || '—'}</td>
                  <td className={`${styles.td} ${styles.gradeCell} ${priceMode === 'psa10_price' ? styles.activePriceCol : ''}`}>{fmt(card.psa10_price)}</td>
                  <td className={`${styles.td} ${styles.gradeCell} ${priceMode === 'psa9_price'  ? styles.activePriceCol : ''}`}>{fmt(card.psa9_price)}</td>
                  <td className={`${styles.td} ${styles.gradeCell} ${priceMode === 'psa8_price'  ? styles.activePriceCol : ''}`}>{fmt(card.psa8_price)}</td>
                  <td className={`${styles.td} ${styles.gradeCell} ${priceMode === 'bgs10_price' ? styles.activePriceCol : ''}`}>{fmt(card.bgs10_price)}</td>
                  <td className={`${styles.td} ${styles.gradeCell} ${priceMode === 'bgs95_price' ? styles.activePriceCol : ''}`}>{fmt(card.bgs95_price)}</td>
                  <td className={`${styles.td} ${styles.gradeCell} ${priceMode === 'bgs9_price'  ? styles.activePriceCol : ''}`}>{fmt(card.bgs9_price)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      {/* ── Analytics Section ── */}
      {!loading && !error && cards.length > 0 && (
        <AnalyticsPanel
          cards={cards} filtered={filtered} priceMode={priceMode}
          nhlStats={nhlStats} seasonalTrends={seasonalTrends}
        />
      )}
    </div>
  )
}


// ── Analytics Panel ─────────────────────────────────────────────────────────

function AnalyticsPanel({ cards, filtered, priceMode, nhlStats, seasonalTrends }) {
  const [openSections, setOpenSections] = useState(new Set())
  const toggle = key => setOpenSections(prev => {
    const next = new Set(prev)
    next.has(key) ? next.delete(key) : next.add(key)
    return next
  })

  const priceLabel = PRICE_MODES.find(p => p.key === priceMode)?.label || 'Raw'

  return (
    <div className={styles.analytics}>
      <div className={styles.analyticsHeader}>
        <span className={styles.analyticsIcon}>📊</span>
        <span className={styles.analyticsTitle}>Young Guns Analytics</span>
        <span className={styles.analyticsModeLabel}>Price Mode</span>
        <span className={styles.analyticsMode}>{priceLabel}</span>
      </div>

      <AccordionSection title="Market Overview" sectionKey="overview" open={openSections} toggle={toggle}>
        <MarketOverview cards={cards} filtered={filtered} priceMode={priceMode} />
      </AccordionSection>

      <AccordionSection title="Price Analysis" sectionKey="price" open={openSections} toggle={toggle}>
        <PriceAnalysis cards={filtered} priceMode={priceMode} priceLabel={priceLabel} />
      </AccordionSection>

      <AccordionSection
        title={`Grading Analytics (${cards.filter(c => c.psa10_price > 0 || c.psa9_price > 0 || c.psa8_price > 0).length} cards)`}
        sectionKey="grading"
        open={openSections}
        toggle={toggle}
      >
        <GradingAnalytics cards={filtered} />
      </AccordionSection>

      <AccordionSection title="Player Compare Tool" sectionKey="compare" open={openSections} toggle={toggle}>
        <PlayerCompare cards={cards} priceMode={priceMode} />
      </AccordionSection>

      <AccordionSection title="Correlation Analytics" sectionKey="correlation" open={openSections} toggle={toggle}>
        <CorrelationAnalytics nhlStats={nhlStats} priceMode={priceMode} />
      </AccordionSection>

      <AccordionSection title="Team Premium Analysis" sectionKey="teams" open={openSections} toggle={toggle}>
        <TeamPremium cards={filtered} priceMode={priceMode} priceLabel={priceLabel} />
      </AccordionSection>

      <AccordionSection title="Position Breakdown" sectionKey="position" open={openSections} toggle={toggle}>
        <PositionBreakdown cards={filtered} priceMode={priceMode} />
      </AccordionSection>

      <AccordionSection title="Nationality Analysis" sectionKey="nationality" open={openSections} toggle={toggle}>
        <NationalityAnalysis nhlStats={nhlStats} />
      </AccordionSection>

      {seasonalTrends.length > 0 && (
        <AccordionSection title="Seasonal Trends" sectionKey="seasonal" open={openSections} toggle={toggle}>
          <SeasonalTrends months={seasonalTrends} />
        </AccordionSection>
      )}
    </div>
  )
}

function AccordionSection({ title, sectionKey, open, toggle, children }) {
  const isOpen = open.has(sectionKey)
  return (
    <div className={styles.accordion}>
      <button className={styles.accordionBtn} onClick={() => toggle(sectionKey)}>
        <span className={styles.accordionArrow}>{isOpen ? '▾' : '▸'}</span>
        {title}
      </button>
      {isOpen && <div className={styles.accordionBody}>{children}</div>}
    </div>
  )
}

function MarketOverview({ cards, filtered, priceMode }) {
  const withPrice  = cards.filter(c => (c[priceMode] ?? 0) > 0)
  const prices     = withPrice.map(c => c[priceMode])
  const total      = prices.reduce((s, v) => s + v, 0)
  const avg        = prices.length ? total / prices.length : 0
  const median     = prices.length ? [...prices].sort((a, b) => a - b)[Math.floor(prices.length / 2)] : 0
  const max        = prices.length ? Math.max(...prices) : 0
  const topCard    = withPrice.find(c => c[priceMode] === max)
  const trending   = { up: 0, stable: 0, down: 0 }
  cards.forEach(c => { if (c.trend in trending) trending[c.trend]++ })

  return (
    <div className={styles.overviewGrid}>
      <StatBox label="Cards Tracked"    value={cards.length.toLocaleString()} />
      <StatBox label="With Price Data"  value={withPrice.length.toLocaleString()} />
      <StatBox label="Avg Price"        value={fmt(avg)} />
      <StatBox label="Median Price"     value={fmt(median)} />
      <StatBox label="Highest Price"    value={fmt(max)} sub={topCard?.player} />
      <StatBox label="Trending Up"      value={trending.up}    color="success" />
      <StatBox label="Stable"           value={trending.stable} />
      <StatBox label="Trending Down"    value={trending.down}   color="danger" />
    </div>
  )
}

function PriceAnalysis({ cards, priceMode, priceLabel }) {
  const withPrice = cards.filter(c => (c[priceMode] ?? 0) > 0)
  const buckets = [
    { label: 'Under $5',    min: 0,   max: 5    },
    { label: '$5–$15',      min: 5,   max: 15   },
    { label: '$15–$30',     min: 15,  max: 30   },
    { label: '$30–$50',     min: 30,  max: 50   },
    { label: '$50–$100',    min: 50,  max: 100  },
    { label: '$100–$250',   min: 100, max: 250  },
    { label: 'Over $250',   min: 250, max: Infinity },
  ]
  const counts = buckets.map(b => ({
    ...b,
    count: withPrice.filter(c => c[priceMode] >= b.min && c[priceMode] < b.max).length,
  }))
  const maxCount = Math.max(...counts.map(b => b.count), 1)

  return (
    <div className={styles.priceAnalysis}>
      <p className={styles.analysisSubtitle}>{priceLabel} price distribution ({withPrice.length} cards with data)</p>
      {counts.map(b => (
        <div key={b.label} className={styles.bucketRow}>
          <span className={styles.bucketLabel}>{b.label}</span>
          <div className={styles.bucketBar}>
            <div className={styles.bucketFill} style={{ width: `${(b.count / maxCount) * 100}%` }} />
          </div>
          <span className={styles.bucketCount}>{b.count}</span>
        </div>
      ))}
    </div>
  )
}

function GradingAnalytics({ cards }) {
  const modes = [
    { key: 'psa10_price', label: 'PSA 10', salesKey: 'psa10_sales' },
    { key: 'psa9_price',  label: 'PSA 9',  salesKey: 'psa9_sales' },
    { key: 'psa8_price',  label: 'PSA 8',  salesKey: 'psa8_sales' },
    { key: 'bgs10_price', label: 'BGS 10', salesKey: 'bgs10_sales' },
    { key: 'bgs95_price', label: 'BGS 9.5',salesKey: 'bgs95_sales' },
    { key: 'bgs9_price',  label: 'BGS 9',  salesKey: 'bgs9_sales' },
  ]

  return (
    <div className={styles.gradingGrid}>
      {modes.map(({ key, label, salesKey }) => {
        const withData = cards.filter(c => (c[key] ?? 0) > 0)
        const prices   = withData.map(c => c[key])
        const avg      = prices.length ? prices.reduce((s, v) => s + v, 0) / prices.length : 0
        const raw      = cards.filter(c => c.fair_value > 0 && c[key] > 0)
        const avgMult  = raw.length ? raw.reduce((s, c) => s + c[key] / c.fair_value, 0) / raw.length : 0

        return (
          <div key={key} className={styles.gradeCard}>
            <span className={styles.gradeLabel}>{label}</span>
            <span className={styles.gradeAvg}>{fmt(avg)}</span>
            <span className={styles.gradeCount}>{withData.length} cards</span>
            {avgMult > 0 && <span className={styles.gradeMult}>{avgMult.toFixed(1)}× raw</span>}
          </div>
        )
      })}
    </div>
  )
}

function PlayerCompare({ cards, priceMode }) {
  const [playerA, setPlayerA] = useState('')
  const [playerB, setPlayerB] = useState('')

  const players = useMemo(() =>
    [...new Set(cards.map(c => c.player).filter(Boolean))].sort(),
  [cards])

  const getCards = name => cards.filter(c => c.player === name)

  const CompareCol = ({ name }) => {
    if (!name) return <div className={styles.compareEmpty}>Select a player</div>
    const pc = getCards(name)
    if (!pc.length) return <div className={styles.compareEmpty}>No data</div>
    const prices = pc.map(c => c[priceMode]).filter(v => v > 0)
    const avg    = prices.length ? prices.reduce((s, v) => s + v, 0) / prices.length : 0
    const max    = prices.length ? Math.max(...prices) : 0
    const owned  = pc.filter(c => c.owned).length
    const up     = pc.filter(c => c.trend === 'up').length
    return (
      <div className={styles.compareCol}>
        <div className={styles.compareName}>{name}</div>
        <StatBox label="Cards in DB" value={pc.length} />
        <StatBox label="Avg Price"   value={fmt(avg)} />
        <StatBox label="Peak"        value={fmt(max)} />
        <StatBox label="Owned"       value={owned} />
        <StatBox label="Trending Up" value={`${up} / ${pc.length}`} color="success" />
      </div>
    )
  }

  return (
    <div className={styles.compareWrap}>
      <div className={styles.compareSelectors}>
        <select className={styles.filterSelect} value={playerA} onChange={e => setPlayerA(e.target.value)}>
          <option value="">Player A</option>
          {players.map(p => <option key={p} value={p}>{p}</option>)}
        </select>
        <span className={styles.compareVs}>vs</span>
        <select className={styles.filterSelect} value={playerB} onChange={e => setPlayerB(e.target.value)}>
          <option value="">Player B</option>
          {players.map(p => <option key={p} value={p}>{p}</option>)}
        </select>
      </div>
      <div className={styles.compareCols}>
        <CompareCol name={playerA} />
        <CompareCol name={playerB} />
      </div>
    </div>
  )
}

function StatBox({ label, value, sub, color }) {
  const cls = color === 'success' ? styles.statSuccess : color === 'danger' ? styles.statDanger : ''
  return (
    <div className={styles.statBox}>
      <span className={styles.statBoxLabel}>{label}</span>
      <span className={`${styles.statBoxValue} ${cls}`}>{value}</span>
      {sub && <span className={styles.statBoxSub}>{sub}</span>}
    </div>
  )
}

// ── Correlation Analytics ─────────────────────────────────────────────────────
function CorrelationAnalytics({ nhlStats, priceMode }) {
  const [tab, setTab] = useState('points')
  const tabs = [
    { key: 'points',   label: 'Points vs Value' },
    { key: 'goals',    label: 'Goals vs Value' },
    { key: 'draft',    label: 'Draft Position' },
    { key: 'value',    label: 'Value Finder' },
  ]

  const scatterData = useMemo(() => {
    return nhlStats
      .filter(p => p.fair_value > 0 && p.points != null)
      .map(p => ({
        name: p.player,
        points: p.points,
        goals: p.goals,
        value: p.fair_value,
        draft: p.draft_overall,
        position: p.position,
      }))
  }, [nhlStats])

  const getX = d => tab === 'goals' ? d.goals : tab === 'draft' ? d.draft : d.points
  const xLabel = tab === 'goals' ? 'Goals' : tab === 'draft' ? 'Draft Pick #' : 'Points'

  // Value Finder: avg price per point-tier
  const valueFinder = useMemo(() => {
    if (tab !== 'value') return []
    const tiers = [
      { label: '0–10 pts', min: 0,  max: 10  },
      { label: '11–20',    min: 11, max: 20  },
      { label: '21–30',    min: 21, max: 30  },
      { label: '31–40',    min: 31, max: 40  },
      { label: '41–50',    min: 41, max: 50  },
      { label: '51+',      min: 51, max: 999 },
    ]
    return tiers.map(t => {
      const bucket = scatterData.filter(d => d.points >= t.min && d.points <= t.max)
      const avg = bucket.length ? bucket.reduce((s, d) => s + d.value, 0) / bucket.length : 0
      return { label: t.label, avg: Math.round(avg * 100) / 100, count: bucket.length }
    }).filter(t => t.count > 0)
  }, [scatterData, tab])

  return (
    <div className={styles.corrWrap}>
      <div className={styles.corrTabs}>
        {tabs.map(t => (
          <button key={t.key}
            className={`${styles.corrTab} ${tab === t.key ? styles.corrTabActive : ''}`}
            onClick={() => setTab(t.key)}
          >{t.label}</button>
        ))}
      </div>

      {tab !== 'value' ? (
        <>
          <p className={styles.corrHint}>
            {scatterData.length} players with both card price and current-season stats.
            {tab === 'draft' && ' Lower pick number = higher draft position.'}
          </p>
          <ResponsiveContainer width="100%" height={280}>
            <ScatterChart margin={{ top: 8, right: 24, left: 0, bottom: 8 }}>
              <CartesianGrid stroke="rgba(255,255,255,0.05)" />
              <XAxis
                type="number" dataKey={d => getX(d)} name={xLabel}
                tick={{ fill: '#9aa0b4', fontSize: 11 }} label={{ value: xLabel, position: 'insideBottom', offset: -4, fill: '#9aa0b4', fontSize: 11 }}
              />
              <YAxis
                type="number" dataKey="value" name="Card Value ($)"
                tick={{ fill: '#9aa0b4', fontSize: 11 }} label={{ value: 'Value ($)', angle: -90, position: 'insideLeft', fill: '#9aa0b4', fontSize: 11 }}
              />
              <Tooltip
                contentStyle={{ background: 'var(--bg-card)', border: '1px solid var(--border)', borderRadius: 8, fontSize: 12 }}
                formatter={(v, k) => [k === 'value' ? `$${v.toFixed(2)}` : v, k === 'value' ? 'Card Value' : xLabel]}
                labelFormatter={(_, payload) => payload?.[0]?.payload?.name || ''}
              />
              <Scatter data={scatterData} fill="#4f8ef7" opacity={0.7} />
            </ScatterChart>
          </ResponsiveContainer>
        </>
      ) : (
        <>
          <p className={styles.corrHint}>Average card value per points-scored tier</p>
          <ResponsiveContainer width="100%" height={220}>
            <BarChart data={valueFinder} margin={{ top: 8, right: 16, left: 0, bottom: 8 }}>
              <XAxis dataKey="label" tick={{ fill: '#9aa0b4', fontSize: 11 }} />
              <YAxis tick={{ fill: '#9aa0b4', fontSize: 11 }} />
              <Tooltip
                contentStyle={{ background: 'var(--bg-card)', border: '1px solid var(--border)', borderRadius: 8, fontSize: 12 }}
                formatter={v => [`$${v.toFixed(2)}`, 'Avg Value']}
              />
              <Bar dataKey="avg" fill="#4f8ef7" radius={[6,6,0,0]} />
            </BarChart>
          </ResponsiveContainer>
        </>
      )}
    </div>
  )
}

// ── Team Premium ──────────────────────────────────────────────────────────────
function TeamPremium({ cards, priceMode, priceLabel }) {
  const teamData = useMemo(() => {
    const groups = {}
    cards.forEach(c => {
      const t = c.team || 'Unknown'
      if (!groups[t]) groups[t] = []
      if ((c[priceMode] ?? 0) > 0) groups[t].push(c[priceMode])
    })
    return Object.entries(groups)
      .map(([team, prices]) => ({
        team: team.replace('Hockey Club', '').replace('Hockey Team', '').trim(),
        avg:  prices.length ? prices.reduce((s, v) => s + v, 0) / prices.length : 0,
        count: prices.length,
      }))
      .filter(t => t.count >= 2)
      .sort((a, b) => b.avg - a.avg)
      .slice(0, 15)
  }, [cards, priceMode])

  return (
    <div>
      <p className={styles.corrHint}>Average {priceLabel} price by team (min 2 cards)</p>
      <ResponsiveContainer width="100%" height={320}>
        <BarChart data={teamData} layout="vertical" margin={{ top: 4, right: 16, left: 100, bottom: 4 }}>
          <XAxis type="number" tick={{ fill: '#9aa0b4', fontSize: 11 }} />
          <YAxis type="category" dataKey="team" tick={{ fill: '#9aa0b4', fontSize: 10 }} width={96} />
          <Tooltip
            contentStyle={{ background: 'var(--bg-card)', border: '1px solid var(--border)', borderRadius: 8, fontSize: 12 }}
            formatter={v => [`$${Number(v).toFixed(2)}`, 'Avg Price']}
          />
          <Bar dataKey="avg" fill="#7c5cbf" radius={[0,6,6,0]} />
        </BarChart>
      </ResponsiveContainer>
    </div>
  )
}

// ── Position Breakdown ────────────────────────────────────────────────────────
function PositionBreakdown({ cards, priceMode }) {
  const posData = useMemo(() => {
    const positions = { 'C': [], 'L': [], 'R': [], 'D': [], 'G': [] }
    const labels = { C: 'Centre', L: 'Left Wing', R: 'Right Wing', D: 'Defence', G: 'Goalie' }
    cards.forEach(c => {
      const p = c.position
      if (p && p in positions && (c[priceMode] ?? 0) > 0) positions[p].push(c[priceMode])
    })
    return Object.entries(positions)
      .filter(([, v]) => v.length > 0)
      .map(([pos, prices]) => ({
        position: labels[pos] || pos,
        avg:   prices.reduce((s, v) => s + v, 0) / prices.length,
        max:   Math.max(...prices),
        count: prices.length,
      }))
      .sort((a, b) => b.avg - a.avg)
  }, [cards, priceMode])

  return (
    <div className={styles.overviewGrid}>
      {posData.map(p => (
        <StatBox
          key={p.position}
          label={p.position}
          value={`$${p.avg.toFixed(2)}`}
          sub={`${p.count} cards · peak $${p.max.toFixed(2)}`}
        />
      ))}
    </div>
  )
}

// ── Nationality Analysis ──────────────────────────────────────────────────────
function NationalityAnalysis({ nhlStats }) {
  const natData = useMemo(() => {
    const groups = {}
    nhlStats.forEach(p => {
      const c = p.birth_country || 'Unknown'
      if (!groups[c]) groups[c] = []
      if ((p.fair_value ?? 0) > 0) groups[c].push(p.fair_value)
    })
    return Object.entries(groups)
      .filter(([, v]) => v.length >= 2)
      .map(([country, prices]) => ({
        country,
        avg:   prices.reduce((s, v) => s + v, 0) / prices.length,
        count: prices.length,
      }))
      .sort((a, b) => b.count - a.count)
      .slice(0, 12)
  }, [nhlStats])

  if (!natData.length) return <p className={styles.corrHint}>No nationality data available.</p>

  return (
    <div>
      <p className={styles.corrHint}>Card count and avg price by player birth country (min 2 cards)</p>
      <ResponsiveContainer width="100%" height={280}>
        <BarChart data={natData} layout="vertical" margin={{ top: 4, right: 16, left: 60, bottom: 4 }}>
          <XAxis type="number" tick={{ fill: '#9aa0b4', fontSize: 11 }} />
          <YAxis type="category" dataKey="country" tick={{ fill: '#9aa0b4', fontSize: 11 }} width={56} />
          <Tooltip
            contentStyle={{ background: 'var(--bg-card)', border: '1px solid var(--border)', borderRadius: 8, fontSize: 12 }}
            formatter={(v, k) => [k === 'avg' ? `$${Number(v).toFixed(2)}` : v, k === 'avg' ? 'Avg Price' : 'Cards']}
          />
          <Legend wrapperStyle={{ fontSize: 12, color: '#9aa0b4' }} />
          <Bar dataKey="count" fill="#4f8ef7" radius={[0,4,4,0]} name="Cards" />
          <Bar dataKey="avg"   fill="#4caf82" radius={[0,4,4,0]} name="Avg Price ($)" />
        </BarChart>
      </ResponsiveContainer>
    </div>
  )
}

// ── Seasonal Trends ───────────────────────────────────────────────────────────
function SeasonalTrends({ months }) {
  return (
    <div>
      <p className={styles.corrHint}>Average YG card price across all cards, by month</p>
      <ResponsiveContainer width="100%" height={240}>
        <LineChart data={months} margin={{ top: 8, right: 24, left: 0, bottom: 8 }}>
          <CartesianGrid stroke="rgba(255,255,255,0.05)" />
          <XAxis dataKey="month" tick={{ fill: '#9aa0b4', fontSize: 10 }} />
          <YAxis tick={{ fill: '#9aa0b4', fontSize: 11 }} />
          <Tooltip
            contentStyle={{ background: 'var(--bg-card)', border: '1px solid var(--border)', borderRadius: 8, fontSize: 12 }}
            formatter={(v, k) => [`$${Number(v).toFixed(2)}`, k === 'avg_price' ? 'Avg Price' : 'Max Price']}
          />
          <Legend wrapperStyle={{ fontSize: 12, color: '#9aa0b4' }} />
          <Line type="monotone" dataKey="avg_price" stroke="#4f8ef7" strokeWidth={2} dot={false} name="Avg Price" />
          <Line type="monotone" dataKey="max_price" stroke="#7c5cbf" strokeWidth={1.5} dot={false} name="Max Price" strokeDasharray="4 2" />
        </LineChart>
      </ResponsiveContainer>
    </div>
  )
}
