import { useState, useEffect, useMemo } from 'react'
import { useNavigate } from 'react-router-dom'
import { BarChart, Bar, XAxis, YAxis, Tooltip, ResponsiveContainer, Cell } from 'recharts'
import PriceChart from '../components/PriceChart'
import TrendBadge from '../components/TrendBadge'
import { getPortfolioHistory, getCards, getCardOfTheDay } from '../api/cards'
import { useCurrency } from '../context/CurrencyContext'
import CurrencySelect from '../components/CurrencySelect'
import pageStyles from './Page.module.css'
import styles from './Portfolio.module.css'

const TREND_COLORS = {
  up:       '#4caf82',
  stable:   '#4f8ef7',
  down:     '#e05c5c',
  'no data':'#9aa0b4',
}

export default function Portfolio() {
  const navigate = useNavigate()

  const [history, setHistory] = useState([])
  const [cards,   setCards]   = useState([])
  const [cotd,    setCotd]    = useState(null)
  const [loading, setLoading] = useState(true)
  const [error,   setError]   = useState(null)

  useEffect(() => {
    Promise.all([getPortfolioHistory(), getCards(), getCardOfTheDay()])
      .then(([ph, cd, cotdData]) => {
        setHistory(ph.history || [])
        setCards(cd.cards || [])
        setCotd(cotdData)
      })
      .catch(e => setError(e.message))
      .finally(() => setLoading(false))
  }, [])

  const latest = history[history.length - 1]

  const stats = useMemo(() => {
    const totalValue   = cards.reduce((s, c) => s + (c.fair_value ?? 0), 0)
    const totalCost    = cards.reduce((s, c) => s + (c.cost_basis  ?? 0), 0)
    const withSales    = cards.filter(c => (c.num_sales ?? 0) > 0).length
    const gainLoss     = totalValue - totalCost
    const avgValue     = cards.length ? totalValue / cards.length : 0

    const trendCounts = { up: 0, stable: 0, down: 0, 'no data': 0 }
    cards.forEach(c => {
      const t = (c.trend || 'no data').toLowerCase()
      trendCounts[t in trendCounts ? t : 'no data']++
    })

    const top10 = [...cards]
      .filter(c => c.fair_value > 0)
      .sort((a, b) => (b.fair_value ?? 0) - (a.fair_value ?? 0))
      .slice(0, 10)

    // Gainers / losers — cards with both cost_basis and fair_value
    const withBoth = cards.filter(c => c.cost_basis > 0 && c.fair_value > 0)
    const withGain = withBoth.map(c => ({ ...c, gain: c.fair_value - c.cost_basis, roi: ((c.fair_value - c.cost_basis) / c.cost_basis) * 100 }))
    const topGainers = [...withGain].sort((a, b) => b.gain - a.gain).slice(0, 5)
    const topLosers  = [...withGain].sort((a, b) => a.gain - b.gain).slice(0, 5)

    return { totalValue, totalCost, gainLoss, avgValue, withSales, trendCounts, top10, topGainers, topLosers }
  }, [cards])

  const { fmtPrice } = useCurrency()
  const trendBarData = Object.entries(stats.trendCounts).map(([trend, count]) => ({ trend, count }))

  return (
    <div className={pageStyles.page}>
      <div className={pageStyles.header}>
        <h1 className={pageStyles.title}>Portfolio</h1>
        <CurrencySelect />
      </div>

      {loading && <p className={pageStyles.status}>Loading…</p>}
      {error   && <p className={pageStyles.error}>Error: {error}</p>}

      {!loading && !error && (<>

        {/* ── Summary stats ── */}
        <div className={styles.stats}>
          <StatCard label="Total Value"   value={fmtPrice(stats.totalValue)} large />
          <StatCard label="Total Cost"    value={fmtPrice(stats.totalCost)} />
          <StatCard
            label="Gain / Loss"
            value={`${stats.gainLoss >= 0 ? '+' : ''}${fmtPrice(stats.gainLoss)}`}
            color={stats.gainLoss >= 0 ? 'success' : 'danger'}
          />
          <StatCard label="Avg per Card"  value={fmtPrice(stats.avgValue)} />
          <StatCard label="Cards"         value={cards.length} />
          <StatCard label="With Sales"    value={stats.withSales} />
        </div>

        {/* ── Value over time chart ── */}
        <div className={styles.section}>
          {history.length <= 1 ? (
            <div className={styles.chartPlaceholder}>
              <p className={styles.placeholderMsg}>
                Portfolio value chart will build up as daily scrapes run.<br />
                {latest && <span>Current snapshot: <strong>{fmtPrice(latest.total_value)}</strong> on {latest.date}</span>}
              </p>
            </div>
          ) : (
            <PriceChart
              data={history.map(h => ({ date: h.date, price: h.total_value }))}
              title="Portfolio Value Over Time"
            />
          )}
        </div>

        {/* ── Two-column lower section ── */}
        <div className={styles.lower}>

          {/* Trend breakdown */}
          <div className={styles.card}>
            <h2 className={styles.cardTitle}>Trend Breakdown</h2>
            <div className={styles.trendSummary}>
              {trendBarData.map(({ trend, count }) => (
                <div key={trend} className={styles.trendRow}>
                  <TrendBadge trend={trend} />
                  <div className={styles.trendBar}>
                    <div
                      className={styles.trendFill}
                      style={{
                        width: `${cards.length ? (count / cards.length) * 100 : 0}%`,
                        background: TREND_COLORS[trend] || '#9aa0b4',
                      }}
                    />
                  </div>
                  <span className={styles.trendCount}>{count}</span>
                </div>
              ))}
            </div>

            <ResponsiveContainer width="100%" height={140}>
              <BarChart data={trendBarData} margin={{ top: 8, right: 0, left: -20, bottom: 0 }}>
                <XAxis dataKey="trend" tick={{ fill: 'var(--text-secondary)', fontSize: 11 }} axisLine={false} tickLine={false} />
                <YAxis tick={{ fill: 'var(--text-secondary)', fontSize: 11 }} axisLine={false} tickLine={false} />
                <Tooltip
                  contentStyle={{ background: 'var(--bg-card)', border: '1px solid var(--border)', borderRadius: 8, fontSize: 12 }}
                  cursor={{ fill: 'rgba(255,255,255,0.04)' }}
                />
                <Bar dataKey="count" radius={[4, 4, 0, 0]}>
                  {trendBarData.map(({ trend }) => (
                    <Cell key={trend} fill={TREND_COLORS[trend] || '#9aa0b4'} />
                  ))}
                </Bar>
              </BarChart>
            </ResponsiveContainer>
          </div>

          {/* Top 10 by value */}
          <div className={styles.card}>
            <h2 className={styles.cardTitle}>Top 10 by Value</h2>
            <table className={styles.topTable}>
              <thead>
                <tr>
                  <th className={styles.topTh}>#</th>
                  <th className={styles.topTh}>Card</th>
                  <th className={styles.topTh}>Value</th>
                  <th className={styles.topTh}>Trend</th>
                </tr>
              </thead>
              <tbody>
                {stats.top10.map((card, i) => (
                  <tr
                    key={card.card_name}
                    className={styles.topRow}
                    onClick={() => navigate(`/ledger/${encodeURIComponent(card.card_name)}`)}
                    title="Click to inspect"
                  >
                    <td className={`${styles.topTd} ${styles.rankCell}`}>{i + 1}</td>
                    <td className={`${styles.topTd} ${styles.nameCell}`}>{card.card_name}</td>
                    <td className={`${styles.topTd} ${styles.valueCell}`}>{fmtPrice(card.fair_value)}</td>
                    <td className={styles.topTd}><TrendBadge trend={card.trend} /></td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>

        </div>

        {/* ── Card of the Day ── */}
        {cotd?.card && (
          <div
            className={styles.cotd}
            onClick={() => navigate(`/ledger/${encodeURIComponent(cotd.card.card_name)}`)}
            title="Click to inspect"
          >
            <span className={styles.cotdIcon}>🃏</span>
            <div className={styles.cotdBody}>
              <span className={styles.cotdLabel}>Card of the Day — {cotd.date}</span>
              <span className={styles.cotdName}>{cotd.card.card_name}</span>
              <span className={styles.cotdValue}>{fmtPrice(cotd.card.fair_value)}</span>
            </div>
            <TrendBadge trend={cotd.card.trend} />
          </div>
        )}

        {/* ── Gainers / Losers ── */}
        {(stats.topGainers.length > 0 || stats.topLosers.length > 0) && (
          <div className={styles.lower} style={{ marginTop: 16 }}>
            <GainLossTable title="Top Gainers" rows={stats.topGainers} navigate={navigate} fmtPrice={fmtPrice} positive />
            <GainLossTable title="Top Losers"  rows={stats.topLosers}  navigate={navigate} fmtPrice={fmtPrice} />
          </div>
        )}

        {/* ── Recently Scraped ── */}
        <RecentlyScraped cards={cards} navigate={navigate} fmtPrice={fmtPrice} />

      </>)}
    </div>
  )
}

function GainLossTable({ title, rows, navigate, fmtPrice, positive }) {
  return (
    <div className={styles.card}>
      <h2 className={styles.cardTitle}>{title}</h2>
      <table className={styles.topTable}>
        <thead>
          <tr>
            <th className={styles.topTh}>Card</th>
            <th className={styles.topTh}>Gain/Loss</th>
            <th className={styles.topTh}>ROI</th>
          </tr>
        </thead>
        <tbody>
          {rows.map(card => (
            <tr
              key={card.card_name}
              className={styles.topRow}
              onClick={() => navigate(`/ledger/${encodeURIComponent(card.card_name)}`)}
            >
              <td className={`${styles.topTd} ${styles.nameCell}`}>{card.card_name}</td>
              <td className={`${styles.topTd}`} style={{ color: positive ? 'var(--success)' : 'var(--danger)', fontWeight: 700 }}>
                {card.gain >= 0 ? '+' : ''}{fmtPrice(card.gain)}
              </td>
              <td className={`${styles.topTd}`} style={{ color: positive ? 'var(--success)' : 'var(--danger)' }}>
                {card.roi >= 0 ? '+' : ''}{card.roi.toFixed(1)}%
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}

function RecentlyScraped({ cards, navigate, fmtPrice }) {
  const recent = [...cards]
    .filter(c => c.last_scraped)
    .sort((a, b) => b.last_scraped.localeCompare(a.last_scraped))
    .slice(0, 5)
  if (!recent.length) return null
  return (
    <div className={styles.card} style={{ marginTop: 16 }}>
      <h2 className={styles.cardTitle}>Recently Scraped</h2>
      <table className={styles.topTable}>
        <thead>
          <tr>
            <th className={styles.topTh}>Card</th>
            <th className={styles.topTh}>Scraped</th>
            <th className={styles.topTh}>Value</th>
            <th className={styles.topTh}>Trend</th>
          </tr>
        </thead>
        <tbody>
          {recent.map(card => (
            <tr
              key={card.card_name}
              className={styles.topRow}
              onClick={() => navigate(`/ledger/${encodeURIComponent(card.card_name)}`)}
              title="Click to inspect"
            >
              <td className={`${styles.topTd} ${styles.nameCell}`}>{card.card_name}</td>
              <td className={styles.topTd}>{card.last_scraped}</td>
              <td className={`${styles.topTd} ${styles.valueCell}`}>{fmtPrice(card.fair_value)}</td>
              <td className={styles.topTd}><TrendBadge trend={card.trend} /></td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}

function StatCard({ label, value, large, color }) {
  const cls = color === 'success' ? styles.success : color === 'danger' ? styles.danger : ''
  return (
    <div className={styles.stat}>
      <span className={styles.statLabel}>{label}</span>
      <span className={`${styles.statValue} ${large ? styles.large : ''} ${cls}`}>{value}</span>
    </div>
  )
}
