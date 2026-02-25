import { useState, useEffect } from 'react'
import { useNavigate } from 'react-router-dom'
import CardTable from '../components/CardTable'
import TrendBadge from '../components/TrendBadge'
import { getCards } from '../api/cards'
import styles from './Page.module.css'

const COLUMNS = [
  { key: 'card_name',   label: 'Card Name' },
  { key: 'fair_value',  label: 'Fair Value',  render: v => v ? `$${Number(v).toFixed(2)}` : '—' },
  { key: 'cost_basis',  label: 'Cost Basis',  render: v => v ? `$${Number(v).toFixed(2)}` : '—' },
  { key: 'trend',       label: 'Trend',       render: v => <TrendBadge trend={v} /> },
  { key: 'num_sales',   label: 'Sales' },
  { key: 'last_sale',   label: 'Last Sale' },
]

export default function CardLedger() {
  const navigate = useNavigate()
  const [cards, setCards] = useState([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(null)
  const [search, setSearch] = useState('')
  const [sortKey, setSortKey] = useState('card_name')
  const [sortDir, setSortDir] = useState('asc')

  useEffect(() => {
    getCards()
      .then(data => setCards(data.cards || []))
      .catch(e => setError(e.message))
      .finally(() => setLoading(false))
  }, [])

  const handleSort = (key) => {
    if (sortKey === key) setSortDir(d => d === 'asc' ? 'desc' : 'asc')
    else { setSortKey(key); setSortDir('asc') }
  }

  const filtered = cards
    .filter(c => c.card_name?.toLowerCase().includes(search.toLowerCase()))
    .sort((a, b) => {
      const av = a[sortKey] ?? ''
      const bv = b[sortKey] ?? ''
      const cmp = String(av).localeCompare(String(bv), undefined, { numeric: true })
      return sortDir === 'asc' ? cmp : -cmp
    })

  return (
    <div className={styles.page}>
      <div className={styles.header}>
        <h1 className={styles.title}>Card Ledger</h1>
        <span className={styles.count}>{cards.length} cards</span>
      </div>

      <div className={styles.toolbar}>
        <input
          className={styles.search}
          placeholder="Search cards..."
          value={search}
          onChange={e => setSearch(e.target.value)}
        />
      </div>

      {loading && <p className={styles.status}>Loading...</p>}
      {error && <p className={styles.error}>Error: {error}</p>}

      {!loading && !error && (
        <CardTable
          columns={COLUMNS}
          rows={filtered}
          sortKey={sortKey}
          sortDir={sortDir}
          onSort={handleSort}
          onRowClick={row => navigate(`/ledger/${encodeURIComponent(row.card_name)}`)}
        />
      )}
    </div>
  )
}
