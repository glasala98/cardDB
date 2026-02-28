import { useState, useEffect, useMemo } from 'react'
import { BarChart, Bar, XAxis, YAxis, Tooltip, ResponsiveContainer, Cell, PieChart, Pie, Legend } from 'recharts'
import { getCards } from '../api/cards'
import { useCurrency } from '../context/CurrencyContext'
import CurrencySelect from '../components/CurrencySelect'
import pageStyles from './Page.module.css'
import styles from './Charts.module.css'

const TREND_COLORS = { up: '#4caf82', stable: '#4f8ef7', down: '#e05c5c', 'no data': '#9aa0b4' }
const GRADE_COLORS = ['#4f8ef7','#7c5cbf','#e0a43c','#4caf82','#e05c5c','#9aa0b4']

export default function Charts() {
  const [cards,   setCards]   = useState([])
  const [loading, setLoading] = useState(true)
  const [error,   setError]   = useState(null)
  const { fmtPrice } = useCurrency()

  useEffect(() => {
    getCards()
      .then(d => setCards(d.cards || []))
      .catch(e => setError(e.message))
      .finally(() => setLoading(false))
  }, [])

  const priceDistribution = useMemo(() => {
    const buckets = [
      { label: 'Under $10',   min: 0,   max: 10   },
      { label: '$10–$25',     min: 10,  max: 25   },
      { label: '$25–$50',     min: 25,  max: 50   },
      { label: '$50–$100',    min: 50,  max: 100  },
      { label: '$100–$250',   min: 100, max: 250  },
      { label: 'Over $250',   min: 250, max: Infinity },
    ]
    return buckets.map(b => ({
      ...b,
      count: cards.filter(c => (c.fair_value ?? 0) >= b.min && (c.fair_value ?? 0) < b.max).length,
    })).filter(b => b.count > 0)
  }, [cards])

  const trendData = useMemo(() => {
    const counts = { up: 0, stable: 0, down: 0, 'no data': 0 }
    cards.forEach(c => {
      const t = (c.trend || 'no data').toLowerCase()
      counts[t in counts ? t : 'no data']++
    })
    return Object.entries(counts).filter(([,v]) => v > 0).map(([name, value]) => ({ name, value }))
  }, [cards])

  const gradeData = useMemo(() => {
    const counts = {}
    cards.forEach(c => {
      const g = c.grade || 'Ungraded'
      counts[g] = (counts[g] || 0) + 1
    })
    return Object.entries(counts)
      .sort((a, b) => b[1] - a[1])
      .slice(0, 8)
      .map(([name, value]) => ({ name, value }))
  }, [cards])

  const setData = useMemo(() => {
    const counts = {}
    cards.forEach(c => {
      const s = c.set_name || 'Unknown'
      counts[s] = (counts[s] || 0) + 1
    })
    return Object.entries(counts)
      .sort((a, b) => b[1] - a[1])
      .slice(0, 10)
      .map(([name, value]) => ({ name: name.length > 20 ? name.slice(0, 18) + '…' : name, full: name, value }))
  }, [cards])

  const costVsValue = useMemo(() =>
    cards
      .filter(c => c.cost_basis > 0 && c.fair_value > 0)
      .map(c => ({
        name: c.player || c.card_name,
        cost: c.cost_basis,
        value: c.fair_value,
        gain: c.fair_value - c.cost_basis,
      }))
      .sort((a, b) => b.gain - a.gain)
      .slice(0, 15)
  , [cards])

  const totalValue  = cards.reduce((s, c) => s + (c.fair_value ?? 0), 0)
  const totalCost   = cards.reduce((s, c) => s + (c.cost_basis  ?? 0), 0)
  const withData    = cards.filter(c => c.fair_value > 0).length
  const notFound    = cards.filter(c => c.confidence === 'not found' || c.confidence === 'notfound').length

  if (loading) return <p className={pageStyles.status}>Loading…</p>
  if (error)   return <p className={pageStyles.error}>Error: {error}</p>

  return (
    <div className={pageStyles.page}>
      <div className={pageStyles.header}>
        <div>
          <h1 className={pageStyles.title}>Charts & Analytics</h1>
          <p className={styles.subtitle}>Visual breakdown of your collection</p>
        </div>
        <CurrencySelect />
      </div>

      {/* Summary stats */}
      <div className={styles.statRow}>
        <StatCard label="Total Cards"    value={cards.length} />
        <StatCard label="With Price Data" value={withData} />
        <StatCard label="Not Found"       value={notFound} color="warn" />
        <StatCard label="Portfolio Value" value={fmtPrice(totalValue)} />
        <StatCard label="Total Cost"      value={fmtPrice(totalCost)} />
        <StatCard label="Unrealized P&L"  value={fmtPrice(totalValue - totalCost)}
          color={totalValue >= totalCost ? 'success' : 'danger'} />
      </div>

      {/* Price Distribution */}
      <div className={styles.chartSection}>
        <h2 className={styles.chartTitle}>Value Distribution</h2>
        <p className={styles.chartSub}>How many cards fall in each price range</p>
        <ResponsiveContainer width="100%" height={240}>
          <BarChart data={priceDistribution} margin={{ top: 4, right: 16, left: 0, bottom: 4 }}>
            <XAxis dataKey="label" tick={{ fill: '#9aa0b4', fontSize: 11 }} />
            <YAxis tick={{ fill: '#9aa0b4', fontSize: 11 }} />
            <Tooltip
              contentStyle={{ background: 'var(--bg-card)', border: '1px solid var(--border)', borderRadius: 8 }}
              formatter={v => [`${v} cards`, 'Count']}
            />
            <Bar dataKey="count" radius={[6,6,0,0]}>
              {priceDistribution.map((_, i) => (
                <Cell key={i} fill={`hsl(${210 + i * 20}, 70%, 60%)`} />
              ))}
            </Bar>
          </BarChart>
        </ResponsiveContainer>
      </div>

      {/* Two-col: Trend + Grade */}
      <div className={styles.twoCol}>
        <div className={styles.chartSection}>
          <h2 className={styles.chartTitle}>Trend Breakdown</h2>
          <ResponsiveContainer width="100%" height={220}>
            <PieChart>
              <Pie data={trendData} dataKey="value" nameKey="name"
                cx="50%" cy="50%" outerRadius={80} label={({ name, percent }) => `${name} ${(percent*100).toFixed(0)}%`}
                labelLine={false}
              >
                {trendData.map((entry, i) => (
                  <Cell key={i} fill={TREND_COLORS[entry.name] || '#9aa0b4'} />
                ))}
              </Pie>
              <Tooltip contentStyle={{ background: 'var(--bg-card)', border: '1px solid var(--border)', borderRadius: 8 }} />
            </PieChart>
          </ResponsiveContainer>
        </div>

        <div className={styles.chartSection}>
          <h2 className={styles.chartTitle}>Grade Distribution</h2>
          <ResponsiveContainer width="100%" height={220}>
            <BarChart data={gradeData} layout="vertical" margin={{ top: 4, right: 16, left: 60, bottom: 4 }}>
              <XAxis type="number" tick={{ fill: '#9aa0b4', fontSize: 11 }} />
              <YAxis type="category" dataKey="name" tick={{ fill: '#9aa0b4', fontSize: 11 }} width={58} />
              <Tooltip contentStyle={{ background: 'var(--bg-card)', border: '1px solid var(--border)', borderRadius: 8 }} />
              <Bar dataKey="value" radius={[0,6,6,0]}>
                {gradeData.map((_, i) => <Cell key={i} fill={GRADE_COLORS[i % GRADE_COLORS.length]} />)}
              </Bar>
            </BarChart>
          </ResponsiveContainer>
        </div>
      </div>

      {/* Top Sets */}
      <div className={styles.chartSection}>
        <h2 className={styles.chartTitle}>Cards by Set</h2>
        <p className={styles.chartSub}>Top 10 sets in your collection</p>
        <ResponsiveContainer width="100%" height={220}>
          <BarChart data={setData} margin={{ top: 4, right: 16, left: 0, bottom: 40 }}>
            <XAxis dataKey="name" tick={{ fill: '#9aa0b4', fontSize: 10 }} angle={-30} textAnchor="end" interval={0} />
            <YAxis tick={{ fill: '#9aa0b4', fontSize: 11 }} />
            <Tooltip
              contentStyle={{ background: 'var(--bg-card)', border: '1px solid var(--border)', borderRadius: 8 }}
              formatter={v => [`${v} cards`, 'Count']}
              labelFormatter={(_, payload) => payload?.[0]?.payload?.full || ''}
            />
            <Bar dataKey="value" fill="#4f8ef7" radius={[6,6,0,0]} />
          </BarChart>
        </ResponsiveContainer>
      </div>

      {/* Cost vs Value */}
      {costVsValue.length > 0 && (
        <div className={styles.chartSection}>
          <h2 className={styles.chartTitle}>Cost vs Current Value (Top 15 by Gain)</h2>
          <ResponsiveContainer width="100%" height={280}>
            <BarChart data={costVsValue} margin={{ top: 4, right: 16, left: 0, bottom: 60 }}>
              <XAxis dataKey="name" tick={{ fill: '#9aa0b4', fontSize: 10 }} angle={-35} textAnchor="end" interval={0} />
              <YAxis tick={{ fill: '#9aa0b4', fontSize: 11 }} />
              <Tooltip
                contentStyle={{ background: 'var(--bg-card)', border: '1px solid var(--border)', borderRadius: 8 }}
                formatter={(v, key) => [fmtPrice(v), key === 'cost' ? 'Cost Basis' : 'Fair Value']}
              />
              <Legend wrapperStyle={{ color: '#9aa0b4', fontSize: 12 }} />
              <Bar dataKey="cost"  fill="#9aa0b4" radius={[4,4,0,0]} name="Cost Basis" />
              <Bar dataKey="value" fill="#4f8ef7" radius={[4,4,0,0]} name="Fair Value" />
            </BarChart>
          </ResponsiveContainer>
        </div>
      )}
    </div>
  )
}

function StatCard({ label, value, color }) {
  const cls = color === 'success' ? styles.statSuccess
    : color === 'danger' ? styles.statDanger
    : color === 'warn'   ? styles.statWarn : ''
  return (
    <div className={styles.statCard}>
      <span className={styles.statLabel}>{label}</span>
      <span className={`${styles.statValue} ${cls}`}>{value}</span>
    </div>
  )
}
