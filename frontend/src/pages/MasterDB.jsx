import { useState, useEffect } from 'react'
import CardTable from '../components/CardTable'
import TrendBadge from '../components/TrendBadge'
import { getYoungGuns } from '../api/masterDb'
import styles from './Page.module.css'

const COLUMNS = [
  { key: 'player',       label: 'Player' },
  { key: 'year',         label: 'Year' },
  { key: 'set',          label: 'Set' },
  { key: 'raw_price',    label: 'Raw Price',   render: v => v ? `$${Number(v).toFixed(2)}` : '—' },
  { key: 'psa10_price',  label: 'PSA 10',      render: v => v ? `$${Number(v).toFixed(2)}` : '—' },
  { key: 'trend',        label: 'Trend',        render: v => <TrendBadge trend={v} /> },
]

export default function MasterDB() {
  const [cards, setCards] = useState([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(null)
  const [search, setSearch] = useState('')

  useEffect(() => {
    getYoungGuns()
      .then(data => setCards(data.cards || []))
      .catch(e => setError(e.message))
      .finally(() => setLoading(false))
  }, [])

  const filtered = cards.filter(c =>
    c.player?.toLowerCase().includes(search.toLowerCase()) ||
    c.year?.toString().includes(search) ||
    c.set?.toLowerCase().includes(search.toLowerCase())
  )

  return (
    <div className={styles.page}>
      <div className={styles.header}>
        <h1 className={styles.title}>Master DB — Young Guns</h1>
        <span className={styles.count}>{cards.length} cards</span>
      </div>

      <div className={styles.toolbar}>
        <input
          className={styles.search}
          placeholder="Search by player, year, set..."
          value={search}
          onChange={e => setSearch(e.target.value)}
        />
      </div>

      {loading && <p className={styles.status}>Loading...</p>}
      {error && <p className={styles.error}>Error: {error}</p>}

      {!loading && !error && (
        <CardTable columns={COLUMNS} rows={filtered} />
      )}
    </div>
  )
}
