import { useState, useEffect } from 'react'
import CardTable from '../components/CardTable'
import { getNHLStats } from '../api/masterDb'
import styles from './Page.module.css'

const COLUMNS = [
  { key: 'player',    label: 'Player' },
  { key: 'team',      label: 'Team' },
  { key: 'position',  label: 'Pos' },
  { key: 'gp',        label: 'GP' },
  { key: 'goals',     label: 'G' },
  { key: 'assists',   label: 'A' },
  { key: 'points',    label: 'PTS' },
  { key: 'plus_minus', label: '+/-' },
  { key: 'shots',      label: 'SOG' },
]

export default function NHLStats() {
  const [players, setPlayers] = useState([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(null)
  const [search, setSearch] = useState('')

  useEffect(() => {
    getNHLStats()
      .then(data => setPlayers(data.players || []))
      .catch(e => setError(e.message))
      .finally(() => setLoading(false))
  }, [])

  const filtered = players.filter(p =>
    p.player?.toLowerCase().includes(search.toLowerCase()) ||
    p.team?.toLowerCase().includes(search.toLowerCase())
  )

  return (
    <div className={styles.page}>
      <div className={styles.header}>
        <h1 className={styles.title}>NHL Player Stats</h1>
      </div>

      <div className={styles.toolbar}>
        <input
          className={styles.search}
          placeholder="Search by player or team..."
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
