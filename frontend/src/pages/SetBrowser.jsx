import { useState, useEffect, useRef } from 'react'
import { useNavigate, useSearchParams } from 'react-router-dom'
import { browseSets, getCatalogFilters } from '../api/catalog'
import styles from './SetBrowser.module.css'

const SPORTS = ['NHL', 'NBA', 'NFL', 'MLB']
const PAGE_SIZE = 60

export default function SetBrowser() {
  const [searchParams] = useSearchParams()
  const navigate = useNavigate()

  const [sport,   setSport]   = useState(searchParams.get('sport') ?? '')
  const [year,    setYear]    = useState(searchParams.get('year')  ?? '')
  const [search,  setSearch]  = useState(searchParams.get('set')   ?? '')
  const [page,    setPage]    = useState(1)

  const [sets,    setSets]    = useState([])
  const [total,   setTotal]   = useState(null)
  const [loading, setLoading] = useState(false)
  const [error,   setError]   = useState(null)
  const [years,   setYears]   = useState([])

  const debounceRef = useRef(null)

  // Load year list when sport changes
  useEffect(() => {
    if (!sport) { setYears([]); setYear(''); return }
    getCatalogFilters(sport).then(d => setYears(d.years ?? [])).catch(() => {})
  }, [sport])

  // Load sets
  useEffect(() => {
    clearTimeout(debounceRef.current)
    debounceRef.current = setTimeout(() => fetchSets(1), 300)
    return () => clearTimeout(debounceRef.current)
  }, [sport, year, search])

  async function fetchSets(pg) {
    setLoading(true)
    const params = { page: pg, per_page: PAGE_SIZE }
    if (sport)  params.sport  = sport
    if (year)   params.year   = year
    if (search) params.search = search
    try {
      setError(null)
      const data = await browseSets(params)
      setSets(data.sets ?? [])
      setTotal(data.total ?? 0)
      setPage(pg)
    } catch (e) {
      setError(e?.message || 'Failed to load sets')
      setSets([])
    } finally { setLoading(false) }
  }

  function goToSet(s) {
    navigate(`/sets/detail?year=${encodeURIComponent(s.year)}&set_name=${encodeURIComponent(s.set_name)}`)
  }

  const totalPages = total != null ? Math.ceil(total / PAGE_SIZE) : 0

  return (
    <div className={styles.page}>
      <div className={styles.header}>
        <h1 className={styles.title}>Set Browser</h1>
        {total != null && <span className={styles.count}>{total.toLocaleString()} sets</span>}
      </div>

      <div className={styles.controls}>
        <div className={styles.sportTabs}>
          <button className={`${styles.sportTab} ${sport === '' ? styles.active : ''}`}
            onClick={() => { setSport(''); setYear('') }}>All</button>
          {SPORTS.map(s => (
            <button key={s} className={`${styles.sportTab} ${sport === s ? styles.active : ''}`}
              onClick={() => { setSport(s); setYear('') }}>{s}</button>
          ))}
        </div>

        <div className={styles.filters}>
          <input
            className={styles.searchInput}
            placeholder="Search set name…"
            value={search}
            onChange={e => setSearch(e.target.value)}
          />
          {years.length > 0 && (
            <select className={styles.yearSelect} value={year} onChange={e => setYear(e.target.value)}>
              <option value="">All years</option>
              {years.map(y => <option key={y} value={y}>{y}</option>)}
            </select>
          )}
        </div>
      </div>

      {loading && <div className={styles.status}><span className={styles.spinner} /> Loading…</div>}

      {error && <div className={styles.error}>{error}</div>}

      {!loading && !error && (
        <>
          <div className={styles.grid}>
            {sets.map((s, i) => (
              <button key={i} className={styles.setCard} onClick={() => goToSet(s)}>
                <div className={styles.setName}>{s.set_name}</div>
                <div className={styles.setYear}>{s.year} · <span className={styles.sportBadge}>{s.sport}</span></div>
                {s.brand && <div className={styles.brand}>{s.brand}</div>}
                <div className={styles.stats}>
                  <span><strong>{s.total_cards?.toLocaleString()}</strong> cards</span>
                  <span><strong>{s.total_variants?.toLocaleString()}</strong> variants</span>
                  <span><strong>{s.total_players?.toLocaleString()}</strong> players</span>
                </div>
              </button>
            ))}
          </div>

          {sets.length === 0 && (
            <div className={styles.empty}>No sets found. Try a different search.</div>
          )}

          {totalPages > 1 && (
            <div className={styles.pagination}>
              <button className={styles.pageBtn} disabled={page <= 1} onClick={() => fetchSets(page - 1)}>← Prev</button>
              <span className={styles.pageInfo}>Page {page} of {totalPages}</span>
              <button className={styles.pageBtn} disabled={page >= totalPages} onClick={() => fetchSets(page + 1)}>Next →</button>
            </div>
          )}
        </>
      )}
    </div>
  )
}
