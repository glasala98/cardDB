import { useState, useEffect, useMemo } from 'react'
import CardTable from '../components/CardTable'
import { getNHLStats } from '../api/masterDb'
import { useCurrency } from '../context/CurrencyContext'
import CurrencySelect from '../components/CurrencySelect'
import styles from './Page.module.css'

const COLUMNS = (fmtPrice) => [
  { key: 'player',       label: 'Player' },
  { key: 'team',         label: 'Team' },
  { key: 'position',     label: 'Pos' },
  { key: 'season',       label: 'Season' },
  { key: 'games_played', label: 'GP' },
  { key: 'goals',        label: 'G' },
  { key: 'assists',      label: 'A' },
  { key: 'points',       label: 'PTS' },
  { key: 'plus_minus',   label: '+/-', render: v => v != null ? (v > 0 ? `+${v}` : v) : '—' },
  { key: 'shots',        label: 'SOG' },
  { key: 'fair_value',  label: 'Raw $',    render: v => v != null ? fmtPrice(v) : '—' },
  { key: 'psa9_price',  label: 'PSA 9 $',  render: v => v != null ? fmtPrice(v) : '—' },
  { key: 'psa10_price', label: 'PSA 10 $', render: v => v != null ? fmtPrice(v) : '—' },
]

export default function NHLStats() {
  const { fmtPrice } = useCurrency()

  const [players,    setPlayers]    = useState([])
  const [loading,    setLoading]    = useState(true)
  const [error,      setError]      = useState(null)
  const [search,     setSearch]     = useState('')
  const [posFilter,  setPosFilter]  = useState('')
  const [teamFilter, setTeamFilter] = useState('')
  const [sortKey,    setSortKey]    = useState('points')
  const [sortDir,    setSortDir]    = useState('desc')

  useEffect(() => {
    getNHLStats()
      .then(data => setPlayers(data.players || []))
      .catch(e => setError(e.message))
      .finally(() => setLoading(false))
  }, [])

  const positions = useMemo(() =>
    [...new Set(players.map(p => p.position).filter(Boolean))].sort()
  , [players])

  const teams = useMemo(() =>
    [...new Set(players.map(p => p.team).filter(Boolean))].sort()
  , [players])

  const filtered = useMemo(() => {
    const s = search.toLowerCase()
    return players
      .filter(p => {
        if (s && !(
          p.player?.toLowerCase().includes(s) ||
          p.team?.toLowerCase().includes(s)
        )) return false
        if (posFilter  && p.position !== posFilter)  return false
        if (teamFilter && p.team     !== teamFilter)  return false
        return true
      })
      .sort((a, b) => {
        const av = a[sortKey] ?? (sortDir === 'desc' ? -Infinity : Infinity)
        const bv = b[sortKey] ?? (sortDir === 'desc' ? -Infinity : Infinity)
        const cmp = typeof av === 'number' && typeof bv === 'number'
          ? av - bv
          : String(av).localeCompare(String(bv))
        return sortDir === 'asc' ? cmp : -cmp
      })
  }, [players, search, posFilter, teamFilter, sortKey, sortDir])

  const handleSort = key => {
    if (sortKey === key) setSortDir(d => d === 'asc' ? 'desc' : 'asc')
    else { setSortKey(key); setSortDir('desc') }
  }

  const withStats  = players.filter(p => p.games_played > 0).length
  const withValues = players.filter(p => p.fair_value  > 0).length

  return (
    <div className={styles.page}>
      <div className={styles.header}>
        <h1 className={styles.title}>NHL Player Stats</h1>
        <span className={styles.count}>{filtered.length} of {players.length} players</span>
        {!loading && withStats > 0 && (
          <span className={styles.count}>{withStats} with stats · {withValues} with card value</span>
        )}
        <CurrencySelect />
      </div>

      <div className={styles.toolbar}>
        <input
          className={styles.search}
          placeholder="Search by player or team…"
          value={search}
          onChange={e => setSearch(e.target.value)}
        />

        <select
          className={styles.filterSelect}
          value={posFilter}
          onChange={e => setPosFilter(e.target.value)}
        >
          <option value="">All Positions</option>
          {positions.map(p => <option key={p} value={p}>{p}</option>)}
        </select>

        <select
          className={styles.filterSelect}
          value={teamFilter}
          onChange={e => setTeamFilter(e.target.value)}
        >
          <option value="">All Teams</option>
          {teams.map(t => <option key={t} value={t}>{t}</option>)}
        </select>

        {(posFilter || teamFilter || search) && (
          <button
            className={styles.clearBtn}
            onClick={() => { setSearch(''); setPosFilter(''); setTeamFilter('') }}
          >
            Clear filters
          </button>
        )}
      </div>

      {loading && <p className={styles.status}>Loading…</p>}
      {error   && <p className={styles.error}>Error: {error}</p>}

      {!loading && !error && (
        <CardTable
          columns={COLUMNS(fmtPrice)}
          rows={filtered}
          sortKey={sortKey}
          sortDir={sortDir}
          onSort={handleSort}
        />
      )}
    </div>
  )
}
