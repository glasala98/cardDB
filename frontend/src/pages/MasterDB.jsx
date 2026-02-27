import { useState, useEffect, useMemo } from 'react'
import { ScatterChart, Scatter, XAxis, YAxis, Tooltip, ResponsiveContainer, CartesianGrid,
         BarChart, Bar, Cell, LineChart, Line, Legend } from 'recharts'
import TrendBadge from '../components/TrendBadge'
import PriceChart from '../components/PriceChart'
import { getYoungGuns, getMarketMovers, getNHLStats, getSeasonalTrends,
         getYGPriceHistoryByName, updateYGOwnership, scrapeYGCard } from '../api/masterDb'
import { useCurrency } from '../context/CurrencyContext'
import CurrencySelect from '../components/CurrencySelect'
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

export default function MasterDB() {
  const { fmtPrice } = useCurrency()
  const fmt = v => v != null && v > 0 ? fmtPrice(v) : '—'

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

  // Selected row (deep-dive)
  const [selectedCard, setSelectedCard] = useState(null)

  const [nhlStats,       setNhlStats]       = useState([])
  const [seasonalTrends, setSeasonalTrends] = useState([])

  const load = () => {
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
  }
  useEffect(load, [])

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
  }, [cards, search, season, team, myCards, sortKey, sortDir])

  const handleSort = key => {
    if (sortKey === key) {
      setSortDir(d => d === 'asc' ? 'desc' : 'asc')
    } else {
      setSortKey(key)
      setSortDir('desc')
      if (PRICE_MODES.some(p => p.key === key)) setPriceMode(key)
    }
  }

  const handleRowClick = card => {
    setSelectedCard(prev => (prev?.player === card.player && prev?.season === card.season) ? null : card)
  }

  const handleOwnershipSaved = (player, season, updated) => {
    setCards(prev => prev.map(c =>
      c.player === player && String(c.season) === String(season)
        ? { ...c, ...updated }
        : c
    ))
    if (selectedCard?.player === player && String(selectedCard?.season) === String(season)) {
      setSelectedCard(prev => ({ ...prev, ...updated }))
    }
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
        <CurrencySelect />
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
            onClick={() => { setPriceMode(key); setSortKey(key); setSortDir('desc') }}
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
        {selectedCard && <span className={styles.deepDiveHint}> · Click a row to inspect · Click again to close</span>}
        {!selectedCard && cards.length > 0 && <span className={styles.deepDiveHint}> · Click any row to inspect</span>}
      </p>

      {myCards && filtered.length > 0 && (
        <MyCardsSummary cards={filtered} priceMode={priceMode} fmt={fmt} />
      )}

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
                <SortTh col={priceMode} label={`${PRICE_MODES.find(p => p.key === priceMode)?.label ?? 'Price'} ($)`} className={styles.activeCol} />
                <SortTh col="num_sales"   label="Sales" />
                <th className={styles.th}>Min ($)</th>
                <th className={styles.th}>Max ($)</th>
                <SortTh col="trend"       label="Trend" />
                <th className={styles.th}>Last Scraped</th>
                <SortTh col="psa10_price" label="PSA 10" />
                <SortTh col="psa9_price"  label="PSA 9" />
                <SortTh col="psa8_price"  label="PSA 8" />
                <SortTh col="bgs10_price" label="BGS 10" />
                <SortTh col="bgs95_price" label="BGS 9.5" />
                <SortTh col="bgs9_price"  label="BGS 9" />
              </tr>
            </thead>
            <tbody>
              {filtered.length === 0 && (
                <tr><td colSpan={16} className={styles.empty}>No cards match the current filters.</td></tr>
              )}
              {filtered.map((card, i) => {
                const isSelected = selectedCard?.player === card.player && selectedCard?.season === card.season
                return (
                  <>
                    <tr
                      key={`${card.season}-${card.card_number}-${i}`}
                      className={`${styles.tr} ${styles.trClickable} ${card.owned ? styles.ownedRow : ''} ${isSelected ? styles.trSelected : ''}`}
                      onClick={() => handleRowClick(card)}
                    >
                      <td className={styles.td}>{card.season}</td>
                      <td className={styles.td}>{card.card_number}</td>
                      <td className={`${styles.td} ${styles.playerCell}`}>{card.player}</td>
                      <td className={styles.td}>{card.team}</td>
                      <td className={`${styles.td} ${styles.priceCell} ${styles.activePriceCol}`}>
                        {fmt(card[priceMode])}
                      </td>
                      <td className={styles.td}>{card.num_sales || '—'}</td>
                      <td className={styles.td}>{fmt(card.min)}</td>
                      <td className={styles.td}>{fmt(card.max)}</td>
                      <td className={styles.td}><TrendBadge trend={card.trend} /></td>
                      <td className={`${styles.td} ${styles.dateCell}`}>{card.last_scraped || '—'}</td>
                      <td className={`${styles.td} ${styles.gradeCell}`}>{fmt(card.psa10_price)}</td>
                      <td className={`${styles.td} ${styles.gradeCell}`}>{fmt(card.psa9_price)}</td>
                      <td className={`${styles.td} ${styles.gradeCell}`}>{fmt(card.psa8_price)}</td>
                      <td className={`${styles.td} ${styles.gradeCell}`}>{fmt(card.bgs10_price)}</td>
                      <td className={`${styles.td} ${styles.gradeCell}`}>{fmt(card.bgs95_price)}</td>
                      <td className={`${styles.td} ${styles.gradeCell}`}>{fmt(card.bgs9_price)}</td>
                    </tr>
                    {isSelected && (
                      <tr key={`${card.season}-${card.card_number}-detail`} className={styles.detailRow}>
                        <td colSpan={16} className={styles.detailCell}>
                          <YGCardDetail
                            card={card}
                            nhlStats={nhlStats}
                            fmt={fmt}
                            onOwnershipSaved={handleOwnershipSaved}
                          />
                        </td>
                      </tr>
                    )}
                  </>
                )
              })}
            </tbody>
          </table>
        </div>
      )}

      {/* ── Analytics Section ── */}
      {!loading && !error && cards.length > 0 && (
        <AnalyticsPanel
          cards={cards} filtered={filtered} priceMode={priceMode}
          nhlStats={nhlStats} seasonalTrends={seasonalTrends}
          movers={movers}
          fmt={fmt}
        />
      )}
    </div>
  )
}


// ── My Cards Portfolio Summary ───────────────────────────────────────────────

function MyCardsSummary({ cards, priceMode, fmt }) {
  const withInvested = cards.filter(c => c.cost_basis > 0)
  const totalInvested = withInvested.reduce((s, c) => s + (c.cost_basis ?? 0), 0)
  const currentValue  = cards.reduce((s, c) => s + (c[priceMode] ?? c.fair_value ?? 0), 0)
  const gainLoss      = currentValue - totalInvested
  const glPct         = totalInvested > 0 ? (gainLoss / totalInvested) * 100 : null
  const positive      = gainLoss >= 0

  return (
    <div className={styles.myCardsSummary}>
      <div className={styles.myCardsStat}>
        <span className={styles.myCardsLabel}>Cards Owned</span>
        <span className={styles.myCardsValue}>{cards.length}</span>
      </div>
      {totalInvested > 0 && (
        <div className={styles.myCardsStat}>
          <span className={styles.myCardsLabel}>Total Invested</span>
          <span className={styles.myCardsValue}>{fmt(totalInvested)}</span>
        </div>
      )}
      <div className={styles.myCardsStat}>
        <span className={styles.myCardsLabel}>Current Value</span>
        <span className={styles.myCardsValue}>{fmt(currentValue)}</span>
      </div>
      {totalInvested > 0 && (
        <div className={styles.myCardsStat}>
          <span className={styles.myCardsLabel}>Gain / Loss</span>
          <span className={`${styles.myCardsValue} ${positive ? styles.myCardsGain : styles.myCardsLoss}`}>
            {gainLoss >= 0 ? '+' : ''}{fmt(gainLoss)}
            {glPct != null && <span className={styles.myCardsPct}> ({glPct >= 0 ? '+' : ''}{glPct.toFixed(1)}%)</span>}
          </span>
        </div>
      )}
    </div>
  )
}


// ── YG Card Deep-Dive Panel ──────────────────────────────────────────────────

function YGCardDetail({ card, nhlStats, fmt, onOwnershipSaved }) {
  const [history,   setHistory]   = useState([])
  const [owned,     setOwned]     = useState(card.owned || false)
  const [cost,      setCost]      = useState(String(card.cost_basis ?? ''))
  const [buyDate,   setBuyDate]   = useState(card.purchase_date || '')
  const [saving,    setSaving]    = useState(false)
  const [saveMsg,   setSaveMsg]   = useState(null)
  const [scraping,  setScraping]  = useState(false)
  const [scrapeMsg, setScrapeMsg] = useState(null)

  useEffect(() => {
    if (card.card_name) {
      getYGPriceHistoryByName(card.card_name)
        .then(r => setHistory(r.history || []))
        .catch(() => {})
    }
  }, [card.card_name])

  // Find matching nhlStats row
  const stats = nhlStats.find(p => p.player === card.player) || {}

  const handleSaveOwnership = async () => {
    setSaving(true)
    try {
      await updateYGOwnership(card.player, card.season, {
        owned,
        cost_basis: cost !== '' ? parseFloat(cost) : null,
        purchase_date: buyDate || null,
      })
      setSaveMsg('Saved!')
      onOwnershipSaved(card.player, card.season, {
        owned,
        cost_basis: cost !== '' ? parseFloat(cost) : null,
        purchase_date: buyDate,
      })
    } catch (e) {
      setSaveMsg('Error: ' + e.message)
    } finally {
      setSaving(false)
      setTimeout(() => setSaveMsg(null), 3000)
    }
  }

  const handleScrape = async () => {
    setScraping(true)
    setScrapeMsg(null)
    try {
      await scrapeYGCard(card.player, card.season)
      setScrapeMsg('Scrape queued — prices will update shortly')
    } catch (e) {
      setScrapeMsg('Scrape failed: ' + e.message)
    } finally {
      setScraping(false)
      setTimeout(() => setScrapeMsg(null), 6000)
    }
  }

  // Chart data for price history
  const chartData = history.map(h => ({
    date: h.date,
    fair_value: h.fair_value ?? null,
  }))

  // Scatter data: each history point as {x: index, y: price, date}
  const scatterPoints = history
    .filter(h => h.fair_value != null)
    .map((h, i) => ({ idx: i + 1, price: h.fair_value, date: h.date }))

  return (
    <div className={styles.detailPanel}>
      <div className={styles.detailGrid}>

        {/* ── Card Info ── */}
        <div className={styles.detailBlock}>
          <h3 className={styles.detailTitle}>{card.player}</h3>
          <p className={styles.detailSub}>{card.season} · #{card.card_number} · {card.team} · {card.position}</p>
          <div className={styles.detailPrices}>
            {[
              { label: 'Raw',     val: card.fair_value },
              { label: 'PSA 9',   val: card.psa9_price },
              { label: 'PSA 10',  val: card.psa10_price },
              { label: 'BGS 9.5', val: card.bgs95_price },
            ].filter(x => x.val > 0).map(x => (
              <div key={x.label} className={styles.detailPriceItem}>
                <span className={styles.detailPriceLabel}>{x.label}</span>
                <span className={styles.detailPriceVal}>{fmt(x.val)}</span>
              </div>
            ))}
          </div>
        </div>

        {/* ── NHL Stats ── */}
        {stats.games_played > 0 && (
          <div className={styles.detailBlock}>
            <h3 className={styles.detailTitle}>Current Season Stats</h3>
            <div className={styles.statsGrid}>
              {[
                { label: 'GP',   val: stats.games_played },
                { label: 'G',    val: stats.goals },
                { label: 'A',    val: stats.assists },
                { label: 'PTS',  val: stats.points },
                { label: '+/-',  val: stats.plus_minus != null ? (stats.plus_minus >= 0 ? `+${stats.plus_minus}` : stats.plus_minus) : null },
                { label: 'SOG',  val: stats.shots },
              ].filter(x => x.val != null).map(x => (
                <div key={x.label} className={styles.statChip}>
                  <span className={styles.statChipVal}>{x.val}</span>
                  <span className={styles.statChipLabel}>{x.label}</span>
                </div>
              ))}
            </div>
            {stats.birth_country && (
              <p className={styles.detailMeta}>
                {stats.birth_country}
                {stats.draft_round && ` · Round ${stats.draft_round} pick #${stats.draft_overall}`}
              </p>
            )}
          </div>
        )}

        {/* ── Ownership Tracker ── */}
        <div className={styles.detailBlock}>
          <h3 className={styles.detailTitle}>Ownership</h3>
          <label className={styles.ownedToggle}>
            <input
              type="checkbox"
              checked={owned}
              onChange={e => setOwned(e.target.checked)}
            />
            I own this card
          </label>
          {owned && (
            <div className={styles.ownershipFields}>
              <label className={styles.ownershipLabel}>
                Cost Basis ($)
                <input
                  type="number" step="0.01" min="0"
                  value={cost} onChange={e => setCost(e.target.value)}
                  className={styles.ownershipInput}
                  placeholder="0.00"
                />
              </label>
              <label className={styles.ownershipLabel}>
                Purchase Date
                <input
                  type="date"
                  value={buyDate} onChange={e => setBuyDate(e.target.value)}
                  className={styles.ownershipInput}
                />
              </label>
            </div>
          )}
          <button
            className={styles.saveOwnershipBtn}
            onClick={handleSaveOwnership}
            disabled={saving}
          >
            {saving ? 'Saving…' : 'Save'}
          </button>
          {saveMsg && <span className={styles.saveMsg}>{saveMsg}</span>}
        </div>
      </div>

      {/* ── Scrape button ── */}
      <div className={styles.detailScrapeRow}>
        <button
          className={styles.scrapeYGBtn}
          onClick={handleScrape}
          disabled={scraping}
        >
          {scraping ? 'Queuing…' : '↻ Scrape eBay'}
        </button>
        {scrapeMsg && (
          <span className={`${styles.saveMsg} ${scrapeMsg.startsWith('Scrape failed') ? styles.scrapeError : ''}`}>
            {scrapeMsg}
          </span>
        )}
      </div>

      {/* ── Price History / Trajectory ── */}
      {chartData.length > 1 && (
        <div className={styles.detailChart}>
          <PriceChart data={chartData} title="Price Trajectory" />

          {/* Raw scrape scatter */}
          <p className={styles.corrHint} style={{ marginTop: 16, marginBottom: 4 }}>
            Price points — each dot is one scrape ({scatterPoints.length} data points)
          </p>
          <ResponsiveContainer width="100%" height={160}>
            <ScatterChart margin={{ top: 4, right: 16, left: 0, bottom: 4 }}>
              <CartesianGrid stroke="rgba(255,255,255,0.05)" />
              <XAxis
                type="number" dataKey="idx" name="Scrape #"
                tick={{ fill: '#9aa0b4', fontSize: 10 }}
                label={{ value: 'Scrape #', position: 'insideBottom', offset: -4, fill: '#9aa0b4', fontSize: 10 }}
              />
              <YAxis
                type="number" dataKey="price" name="Price"
                tick={{ fill: '#9aa0b4', fontSize: 10 }}
                tickFormatter={v => `$${v}`}
              />
              <Tooltip
                contentStyle={{ background: 'var(--bg-card)', border: '1px solid var(--border)', borderRadius: 8, fontSize: 12 }}
                formatter={(v, k) => [k === 'price' ? `$${Number(v).toFixed(2)}` : v, k === 'price' ? 'Price' : 'Scrape #']}
                labelFormatter={(_, payload) => payload?.[0]?.payload?.date || ''}
              />
              <Scatter data={scatterPoints} fill="#4caf82" opacity={0.85} />
            </ScatterChart>
          </ResponsiveContainer>

          {/* Trajectory summary */}
          {scatterPoints.length >= 2 && (() => {
            const first = scatterPoints[0].price
            const last  = scatterPoints[scatterPoints.length - 1].price
            const change = last - first
            const pct    = first > 0 ? ((change / first) * 100).toFixed(1) : null
            const up     = change >= 0
            return (
              <div className={styles.trajectoryRow}>
                <span className={styles.trajectoryLabel}>Over {scatterPoints.length} scrapes:</span>
                <span className={`${styles.trajectoryChange} ${up ? styles.myCardsGain : styles.myCardsLoss}`}>
                  {up ? '+' : ''}{fmt(change)} ({pct !== null ? `${up ? '+' : ''}${pct}%` : '—'})
                </span>
                <span className={styles.trajectoryLabel}>
                  {scatterPoints[0].date} → {scatterPoints[scatterPoints.length - 1].date}
                </span>
                {stats.points != null && (
                  <span className={styles.trajectoryLabel}>
                    · Current season: {stats.points} PTS in {stats.games_played} GP
                  </span>
                )}
                {stats.wins != null && (
                  <span className={styles.trajectoryLabel}>
                    · {stats.wins}W · {stats.save_pct?.toFixed(3)} SV% · {stats.gaa?.toFixed(2)} GAA
                  </span>
                )}
              </div>
            )
          })()}
        </div>
      )}
      {chartData.length <= 1 && card.card_name && (
        <p className={styles.detailNoHistory}>No price history on record yet.</p>
      )}
    </div>
  )
}


// ── Analytics Panel ─────────────────────────────────────────────────────────

function AnalyticsPanel({ cards, filtered, priceMode, nhlStats, seasonalTrends, movers, fmt }) {
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
        <MarketOverview cards={cards} filtered={filtered} priceMode={priceMode} fmt={fmt} />
      </AccordionSection>

      <AccordionSection title="Price Analysis" sectionKey="price" open={openSections} toggle={toggle}>
        <PriceAnalysis cards={filtered} priceMode={priceMode} priceLabel={priceLabel} fmt={fmt} />
      </AccordionSection>

      <AccordionSection
        title={`Grading Analytics (${cards.filter(c => c.psa10_price > 0 || c.psa9_price > 0 || c.psa8_price > 0).length} cards)`}
        sectionKey="grading"
        open={openSections}
        toggle={toggle}
      >
        <GradingAnalytics cards={filtered} fmt={fmt} />
      </AccordionSection>

      <AccordionSection title="Player Compare Tool" sectionKey="compare" open={openSections} toggle={toggle}>
        <PlayerCompare cards={cards} priceMode={priceMode} nhlStats={nhlStats} fmt={fmt} />
      </AccordionSection>

      <AccordionSection title="Correlation Analytics" sectionKey="correlation" open={openSections} toggle={toggle}>
        <CorrelationAnalytics nhlStats={nhlStats} priceMode={priceMode} fmt={fmt} />
      </AccordionSection>

      {(movers.gainers.length > 0 || movers.losers.length > 0) && (
        <AccordionSection title="Price Momentum" sectionKey="momentum" open={openSections} toggle={toggle}>
          <PriceMomentum movers={movers} fmt={fmt} />
        </AccordionSection>
      )}

      <AccordionSection title="Value Finder — Overvalued / Undervalued" sectionKey="valuefinder" open={openSections} toggle={toggle}>
        <ValueFinder nhlStats={nhlStats} fmt={fmt} />
      </AccordionSection>

      <AccordionSection title="Rookie Impact Score" sectionKey="impact" open={openSections} toggle={toggle}>
        <RookieImpactScore nhlStats={nhlStats} fmt={fmt} />
      </AccordionSection>

      <AccordionSection title="Team Premium Analysis" sectionKey="teams" open={openSections} toggle={toggle}>
        <TeamPremium cards={filtered} priceMode={priceMode} priceLabel={priceLabel} fmt={fmt} />
      </AccordionSection>

      <AccordionSection title="Position Breakdown" sectionKey="position" open={openSections} toggle={toggle}>
        <PositionBreakdown cards={filtered} priceMode={priceMode} fmt={fmt} />
      </AccordionSection>

      <AccordionSection title="Nationality Analysis" sectionKey="nationality" open={openSections} toggle={toggle}>
        <NationalityAnalysis nhlStats={nhlStats} fmt={fmt} />
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

function MarketOverview({ cards, filtered, priceMode, fmt }) {
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

function PriceAnalysis({ cards, priceMode, priceLabel, fmt }) {
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

function GradingAnalytics({ cards, fmt }) {
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

// ── Player Compare Tool ───────────────────────────────────────────────────────
function PlayerCompare({ cards, priceMode, nhlStats, fmt }) {
  const [playerA, setPlayerA] = useState('')
  const [playerB, setPlayerB] = useState('')

  const players = useMemo(() =>
    [...new Set(cards.map(c => c.player).filter(Boolean))].sort(),
  [cards])

  const getPlayerCards = name => cards.filter(c => c.player === name)
  const getStats       = name => nhlStats.find(p => p.player === name) || {}

  const CompareCol = ({ name }) => {
    if (!name) return <div className={styles.compareEmpty}>Select a player above</div>
    const pc    = getPlayerCards(name)
    const stats = getStats(name)
    if (!pc.length) return <div className={styles.compareEmpty}>No data</div>
    const prices = pc.map(c => c[priceMode]).filter(v => v > 0)
    const avg    = prices.length ? prices.reduce((s, v) => s + v, 0) / prices.length : 0
    const max    = prices.length ? Math.max(...prices) : 0
    const owned  = pc.filter(c => c.owned).length

    return (
      <div className={styles.compareCol}>
        <div className={styles.compareName}>{name}</div>
        <div className={styles.compareStats}>
          <StatBox label="Cards in DB" value={pc.length} />
          <StatBox label="Avg Price"   value={fmt(avg)} />
          <StatBox label="Peak"        value={fmt(max)} />
          <StatBox label="Owned"       value={owned} />
        </div>
        {stats.games_played > 0 && (
          <div className={styles.compareNHLBlock}>
            <div className={styles.compareNHLTitle}>Current Season</div>
            <div className={styles.statsGrid}>
              {[
                { label: 'GP',  val: stats.games_played },
                { label: 'G',   val: stats.goals },
                { label: 'A',   val: stats.assists },
                { label: 'PTS', val: stats.points },
                { label: '+/-', val: stats.plus_minus != null ? (stats.plus_minus >= 0 ? `+${stats.plus_minus}` : stats.plus_minus) : null },
              ].filter(x => x.val != null).map(x => (
                <div key={x.label} className={styles.statChip}>
                  <span className={styles.statChipVal}>{x.val}</span>
                  <span className={styles.statChipLabel}>{x.label}</span>
                </div>
              ))}
            </div>
            {stats.birth_country && (
              <p className={styles.detailMeta}>{stats.birth_country}
                {stats.draft_round && ` · Rd ${stats.draft_round} #${stats.draft_overall}`}
              </p>
            )}
          </div>
        )}
        {/* Graded prices table */}
        {(pc[0]?.psa10_price > 0 || pc[0]?.psa9_price > 0) && (
          <div className={styles.compareGrades}>
            {[
              { label: 'PSA 10', val: pc[0]?.psa10_price },
              { label: 'PSA 9',  val: pc[0]?.psa9_price },
              { label: 'PSA 8',  val: pc[0]?.psa8_price },
              { label: 'BGS 9.5', val: pc[0]?.bgs95_price },
            ].filter(x => x.val > 0).map(x => (
              <div key={x.label} className={styles.compareGradeRow}>
                <span>{x.label}</span>
                <span className={styles.compareGradeVal}>{fmt(x.val)}</span>
              </div>
            ))}
          </div>
        )}
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
function CorrelationAnalytics({ nhlStats, priceMode, fmt }) {
  const [tab, setTab] = useState('points')
  const tabs = [
    { key: 'points',  label: 'Points vs Value' },
    { key: 'goals',   label: 'Goals vs Value' },
    { key: 'draft',   label: 'Draft Position' },
    { key: 'goalies', label: 'Goalies' },
  ]

  const scatterData = useMemo(() => {
    return nhlStats
      .filter(p => p.fair_value > 0 && p.points != null && p.position !== 'G')
      .map(p => ({
        name:     p.player,
        points:   p.points,
        goals:    p.goals,
        value:    p.fair_value,
        draft:    p.draft_overall,
        round:    p.draft_round,
        position: p.position,
      }))
  }, [nhlStats])

  const goalieData = useMemo(() => {
    return nhlStats
      .filter(p => p.position === 'G' && p.fair_value > 0 && p.games_played > 0)
      .map(p => ({
        name:     p.player,
        wins:     p.wins ?? 0,
        save_pct: p.save_pct ?? 0,
        gaa:      p.gaa ?? 0,
        gp:       p.games_played,
        value:    p.fair_value,
      }))
  }, [nhlStats])

  const [goalieX, setGoalieX] = useState('wins')
  const goalieXLabel = goalieX === 'wins' ? 'Wins' : goalieX === 'save_pct' ? 'Save %' : 'GAA'

  const getX   = d => tab === 'goals' ? d.goals : tab === 'draft' ? d.draft : d.points
  const xLabel = tab === 'goals' ? 'Goals' : tab === 'draft' ? 'Draft Pick #' : 'Points'

  // Draft round breakdown bar chart
  const draftRoundData = useMemo(() => {
    if (tab !== 'draft') return []
    const rounds = {}
    scatterData.forEach(d => {
      const r = d.round ? `Rd ${d.round}` : 'Undrafted'
      if (!rounds[r]) rounds[r] = []
      rounds[r].push(d.value)
    })
    return Object.entries(rounds)
      .map(([round, vals]) => ({
        round,
        avg:   vals.length ? Math.round(vals.reduce((s, v) => s + v, 0) / vals.length * 100) / 100 : 0,
        count: vals.length,
      }))
      .sort((a, b) => {
        const ai = a.round === 'Undrafted' ? 99 : parseInt(a.round.replace('Rd ', ''))
        const bi = b.round === 'Undrafted' ? 99 : parseInt(b.round.replace('Rd ', ''))
        return ai - bi
      })
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

      {tab === 'goalies' ? (
        <>
          <div className={styles.corrTabs} style={{ marginTop: 8 }}>
            {[['wins','Wins'],['save_pct','Save %'],['gaa','GAA']].map(([k, l]) => (
              <button key={k}
                className={`${styles.corrTab} ${goalieX === k ? styles.corrTabActive : ''}`}
                onClick={() => setGoalieX(k)}
                style={{ fontSize: 11 }}
              >{l}</button>
            ))}
          </div>
          <p className={styles.corrHint}>
            {goalieData.length} goalies with card price and current-season stats.
            {goalieX === 'gaa' && ' Lower GAA = better performance.'}
          </p>
          {goalieData.length === 0 ? (
            <p className={styles.corrHint}>No goalie stats available — check NHL stats data.</p>
          ) : (
            <ResponsiveContainer width="100%" height={260}>
              <ScatterChart margin={{ top: 8, right: 24, left: 0, bottom: 20 }}>
                <CartesianGrid stroke="rgba(255,255,255,0.05)" />
                <XAxis
                  type="number" dataKey={d => d[goalieX]} name={goalieXLabel}
                  tick={{ fill: '#9aa0b4', fontSize: 11 }}
                  label={{ value: goalieXLabel, position: 'insideBottom', offset: -10, fill: '#9aa0b4', fontSize: 11 }}
                />
                <YAxis
                  type="number" dataKey="value" name="Card Value ($)"
                  tick={{ fill: '#9aa0b4', fontSize: 11 }}
                  label={{ value: 'Value ($)', angle: -90, position: 'insideLeft', fill: '#9aa0b4', fontSize: 11 }}
                />
                <Tooltip
                  contentStyle={{ background: 'var(--bg-card)', border: '1px solid var(--border)', borderRadius: 8, fontSize: 12 }}
                  formatter={(v, k) => [k === 'value' ? `$${Number(v).toFixed(2)}` : (typeof v === 'number' ? v.toFixed(3) : v), k === 'value' ? 'Card Value' : goalieXLabel]}
                  labelFormatter={(_, payload) => payload?.[0]?.payload?.name || ''}
                />
                <Scatter data={goalieData} fill="#e8a838" opacity={0.8} />
              </ScatterChart>
            </ResponsiveContainer>
          )}
        </>
      ) : (
        <>
          <p className={styles.corrHint}>
            {scatterData.length} skaters with both card price and current-season stats.
            {tab === 'draft' && ' Lower pick number = higher draft position.'}
          </p>
          <ResponsiveContainer width="100%" height={260}>
            <ScatterChart margin={{ top: 8, right: 24, left: 0, bottom: 20 }}>
              <CartesianGrid stroke="rgba(255,255,255,0.05)" />
              <XAxis
                type="number" dataKey={d => getX(d)} name={xLabel}
                tick={{ fill: '#9aa0b4', fontSize: 11 }}
                label={{ value: xLabel, position: 'insideBottom', offset: -10, fill: '#9aa0b4', fontSize: 11 }}
              />
              <YAxis
                type="number" dataKey="value" name="Card Value ($)"
                tick={{ fill: '#9aa0b4', fontSize: 11 }}
                label={{ value: 'Value ($)', angle: -90, position: 'insideLeft', fill: '#9aa0b4', fontSize: 11 }}
              />
              <Tooltip
                contentStyle={{ background: 'var(--bg-card)', border: '1px solid var(--border)', borderRadius: 8, fontSize: 12 }}
                formatter={(v, k) => [k === 'value' ? `$${v.toFixed(2)}` : v, k === 'value' ? 'Card Value' : xLabel]}
                labelFormatter={(_, payload) => payload?.[0]?.payload?.name || ''}
              />
              <Scatter data={scatterData} fill="#4f8ef7" opacity={0.7} />
            </ScatterChart>
          </ResponsiveContainer>

          {tab === 'draft' && draftRoundData.length > 0 && (
            <>
              <p className={styles.corrHint} style={{ marginTop: 16 }}>Average card value by draft round</p>
              <ResponsiveContainer width="100%" height={200}>
                <BarChart data={draftRoundData} margin={{ top: 4, right: 16, left: 0, bottom: 4 }}>
                  <XAxis dataKey="round" tick={{ fill: '#9aa0b4', fontSize: 11 }} />
                  <YAxis tick={{ fill: '#9aa0b4', fontSize: 11 }} />
                  <Tooltip
                    contentStyle={{ background: 'var(--bg-card)', border: '1px solid var(--border)', borderRadius: 8, fontSize: 12 }}
                    formatter={(v, k) => [k === 'avg' ? `$${v.toFixed(2)}` : v, k === 'avg' ? 'Avg Value' : 'Cards']}
                  />
                  <Bar dataKey="avg" fill="#7c5cbf" radius={[6,6,0,0]} name="Avg Value ($)" />
                </BarChart>
              </ResponsiveContainer>
            </>
          )}
        </>
      )}
    </div>
  )
}

// ── Price Momentum ────────────────────────────────────────────────────────────
function PriceMomentum({ movers, fmt }) {
  const [tab, setTab] = useState('gainers')
  const rows = tab === 'gainers' ? movers.gainers : movers.losers

  return (
    <div className={styles.corrWrap}>
      <p className={styles.corrHint}>
        Price change based on most recent vs previous scrape. Requires at least 2 historical data points per card.
      </p>
      <div className={styles.corrTabs}>
        <button
          className={`${styles.corrTab} ${tab === 'gainers' ? styles.corrTabActive : ''}`}
          onClick={() => setTab('gainers')}
        >
          Top Gainers ({movers.gainers.length})
        </button>
        <button
          className={`${styles.corrTab} ${tab === 'losers' ? styles.corrTabActive : ''}`}
          onClick={() => setTab('losers')}
        >
          Top Losers ({movers.losers.length})
        </button>
      </div>
      {rows.length === 0 ? (
        <p className={styles.corrHint}>No movement data yet — needs multiple scrapes.</p>
      ) : (
        <div className={styles.tableWrap} style={{ maxHeight: 320, marginTop: 12 }}>
          <table className={styles.table}>
            <thead>
              <tr>
                <th className={styles.th}>Card</th>
                <th className={styles.th}>Previous</th>
                <th className={styles.th}>Current</th>
                <th className={styles.th}>Change</th>
                <th className={styles.th}>Change %</th>
              </tr>
            </thead>
            <tbody>
              {rows.map((m, i) => {
                const up = m.direction === 'up'
                return (
                  <tr key={i} className={styles.tr}>
                    <td className={`${styles.td} ${styles.playerCell}`}>{m.card_name}</td>
                    <td className={styles.td}>{fmt(m.old_price)}</td>
                    <td className={styles.td}>{fmt(m.new_price)}</td>
                    <td className={`${styles.td} ${up ? styles.premiumUnder : styles.premiumOver}`}>
                      {up ? '+' : ''}{fmt(m.new_price - m.old_price)}
                    </td>
                    <td className={`${styles.td} ${up ? styles.premiumUnder : styles.premiumOver}`}>
                      {m.pct_change >= 0 ? '+' : ''}{m.pct_change}%
                    </td>
                  </tr>
                )
              })}
            </tbody>
          </table>
        </div>
      )}
    </div>
  )
}


// ── Value Finder ──────────────────────────────────────────────────────────────
function ValueFinder({ nhlStats, fmt }) {
  const [tab, setTab] = useState('under')

  const data = useMemo(() => {
    const players = nhlStats.filter(p => p.fair_value > 0 && p.points != null && p.games_played > 0)

    // Compute point-tier expected price
    const tiers = [
      { min: 0,  max: 10  },
      { min: 11, max: 20  },
      { min: 21, max: 30  },
      { min: 31, max: 40  },
      { min: 41, max: 50  },
      { min: 51, max: 999 },
    ]
    const tierAvg = tiers.map(t => {
      const bucket = players.filter(p => p.points >= t.min && p.points <= t.max)
      return {
        ...t,
        avg: bucket.length ? bucket.reduce((s, p) => s + p.fair_value, 0) / bucket.length : 0,
      }
    })

    return players.map(p => {
      const tier   = tierAvg.find(t => p.points >= t.min && p.points <= t.max)
      const expect = tier?.avg || 0
      const premium = expect > 0 ? Math.round((p.fair_value - expect) / expect * 100) : 0
      return { ...p, expected: expect, premium }
    }).filter(p => p.expected > 0)
  }, [nhlStats])

  const overvalued  = useMemo(() => [...data].sort((a, b) => b.premium - a.premium).slice(0, 12), [data])
  const undervalued = useMemo(() => [...data].sort((a, b) => a.premium - b.premium).slice(0, 12), [data])
  const rows = tab === 'over' ? overvalued : undervalued

  return (
    <div className={styles.corrWrap}>
      <p className={styles.corrHint}>
        Expected price is based on average for players with similar point totals.
        Premium = (Actual − Expected) / Expected × 100%.
      </p>
      <div className={styles.corrTabs}>
        <button className={`${styles.corrTab} ${tab === 'under' ? styles.corrTabActive : ''}`} onClick={() => setTab('under')}>
          Most Undervalued
        </button>
        <button className={`${styles.corrTab} ${tab === 'over' ? styles.corrTabActive : ''}`} onClick={() => setTab('over')}>
          Most Overvalued
        </button>
      </div>
      <div className={styles.tableWrap} style={{ maxHeight: 340, marginTop: 12 }}>
        <table className={styles.table}>
          <thead>
            <tr>
              <th className={styles.th}>Player</th>
              <th className={styles.th}>Team</th>
              <th className={styles.th}>PTS</th>
              <th className={styles.th}>GP</th>
              <th className={styles.th}>Actual $</th>
              <th className={styles.th}>Expected $</th>
              <th className={styles.th}>Premium %</th>
            </tr>
          </thead>
          <tbody>
            {rows.map((p, i) => (
              <tr key={i} className={styles.tr}>
                <td className={`${styles.td} ${styles.playerCell}`}>{p.player}</td>
                <td className={styles.td}>{p.team}</td>
                <td className={styles.td}>{p.points}</td>
                <td className={styles.td}>{p.games_played}</td>
                <td className={styles.td}>{fmt(p.fair_value)}</td>
                <td className={styles.td}>{fmt(p.expected)}</td>
                <td className={`${styles.td} ${p.premium > 0 ? styles.premiumOver : styles.premiumUnder}`}>
                  {p.premium >= 0 ? '+' : ''}{p.premium}%
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  )
}

// ── Rookie Impact Score ───────────────────────────────────────────────────────
function RookieImpactScore({ nhlStats, fmt }) {
  const [sortKey, setSortKey] = useState('score')
  const [sortDir, setSortDir] = useState('desc')

  const scored = useMemo(() => {
    const players = nhlStats.filter(p => p.games_played > 0)
    if (!players.length) return []

    // Raw metrics
    const ptsPace   = players.map(p => p.points / p.games_played)
    const pmRate    = players.map(p => (p.plus_minus ?? 0) / p.games_played)
    const shotPct   = players.map(p => p.shots > 0 ? (p.goals ?? 0) / p.shots : 0)
    const draftInv  = players.map(p => p.draft_overall ? 1 / p.draft_overall : 0)
    const cardVal   = players.map(p => p.fair_value ?? 0)

    const normalize = arr => {
      const mn = Math.min(...arr), mx = Math.max(...arr)
      return mx === mn ? arr.map(() => 0) : arr.map(v => (v - mn) / (mx - mn))
    }

    const nPts  = normalize(ptsPace)
    const nPM   = normalize(pmRate)
    const nShot = normalize(shotPct)
    const nDraft = normalize(draftInv)
    const nVal  = normalize(cardVal)

    return players.map((p, i) => ({
      ...p,
      score: Math.round(
        nPts[i]  * 40 +
        nPM[i]   * 15 +
        nShot[i] * 10 +
        nDraft[i] * 15 +
        nVal[i]  * 20
      ),
      pts_pace: +(p.points / p.games_played).toFixed(2),
    }))
  }, [nhlStats])

  const sorted = useMemo(() => {
    return [...scored].sort((a, b) => {
      const av = a[sortKey] ?? 0
      const bv = b[sortKey] ?? 0
      return sortDir === 'desc' ? bv - av : av - bv
    })
  }, [scored, sortKey, sortDir])

  const handleSort = key => {
    if (sortKey === key) setSortDir(d => d === 'asc' ? 'desc' : 'asc')
    else { setSortKey(key); setSortDir('desc') }
  }

  const SortTh = ({ col, label }) => (
    <th className={styles.th} style={{ cursor: 'pointer' }} onClick={() => handleSort(col)}>
      {label}
      {sortKey === col && <span className={styles.arrow}>{sortDir === 'asc' ? ' ↑' : ' ↓'}</span>}
    </th>
  )

  if (!sorted.length) {
    return <p className={styles.corrHint}>No NHL stats data available for scoring.</p>
  }

  return (
    <div>
      <p className={styles.corrHint}>
        Composite score: Points Pace 40% · Card Market 20% · Draft Position 15% · +/- Rate 15% · Shot % 10%
      </p>
      <div className={styles.tableWrap} style={{ maxHeight: 380 }}>
        <table className={styles.table}>
          <thead>
            <tr>
              <th className={styles.th}>#</th>
              <SortTh col="score"      label="Score" />
              <SortTh col="player"     label="Player" />
              <SortTh col="team"       label="Team" />
              <SortTh col="position"   label="Pos" />
              <SortTh col="games_played" label="GP" />
              <SortTh col="points"     label="PTS" />
              <SortTh col="pts_pace"   label="PTS/G" />
              <SortTh col="goals"      label="G" />
              <SortTh col="fair_value" label="Card $" />
            </tr>
          </thead>
          <tbody>
            {sorted.map((p, i) => (
              <tr key={i} className={`${styles.tr} ${i < 3 ? styles.topThree : ''}`}>
                <td className={styles.td}>{i + 1}</td>
                <td className={`${styles.td} ${styles.impactScore}`}>{p.score}</td>
                <td className={`${styles.td} ${styles.playerCell}`}>{p.player}</td>
                <td className={styles.td}>{p.team}</td>
                <td className={styles.td}>{p.position}</td>
                <td className={styles.td}>{p.games_played}</td>
                <td className={styles.td}>{p.points}</td>
                <td className={styles.td}>{p.pts_pace}</td>
                <td className={styles.td}>{p.goals}</td>
                <td className={styles.td}>{fmt(p.fair_value)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  )
}

// ── Team Premium ──────────────────────────────────────────────────────────────
function TeamPremium({ cards, priceMode, priceLabel, fmt }) {
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
function PositionBreakdown({ cards, priceMode, fmt }) {
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
function NationalityAnalysis({ nhlStats, fmt }) {
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
