import { useState, useEffect, useRef, useCallback } from 'react'
import { useNavigate, useSearchParams } from 'react-router-dom'
import { browseSets, getCatalogFilters } from '../api/catalog'
import styles from './SetBrowser.module.css'

const SPORTS = ['NHL', 'NBA', 'NFL', 'MLB']
const PAGE_SIZE = 60

const SPORT_COLORS = {
  NHL: '#4a9eff',
  NBA: '#ff6b35',
  NFL: '#5cb85c',
  MLB: '#e74c3c',
}

const SPORT_INITIALS = {
  NHL: 'HK',
  NBA: 'BB',
  NFL: 'FB',
  MLB: 'BB',
}

function BoxArt({ imageUrl, year, sport, color }) {
  const [imgFailed, setImgFailed] = useState(false)
  const showImg = imageUrl && !imgFailed
  return (
    <div className={styles.boxArt} style={{ background: `linear-gradient(135deg, ${color}22, ${color}08)`, borderBottom: `2px solid ${color}44` }}>
      {showImg
        ? <img src={imageUrl} alt="" className={styles.boxImg} onError={() => setImgFailed(true)} />
        : <>
            <span className={styles.boxYear}>{year}</span>
            <span className={styles.boxSport} style={{ color }}>{sport}</span>
          </>
      }
    </div>
  )
}

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

  // Reload years when sport or search changes — scope to both; reset year on change
  useEffect(() => {
    setYear('')
    const q = search.length >= 2 ? search : null
    if (!sport && !q) { setYears([]); return }
    getCatalogFilters(sport || null, null, q).then(d => setYears(d.years ?? [])).catch(() => {})
  }, [sport, search]) // eslint-disable-line react-hooks/exhaustive-deps

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

      {/* Filters */}
      <div className={styles.controls}>
        <div className={styles.sportTabs}>
          <button className={`${styles.sportTab} ${sport === '' ? styles.active : ''}`}
            onClick={() => { setSport(''); setYear('') }}>All</button>
          {SPORTS.map(s => (
            <button key={s}
              className={`${styles.sportTab} ${sport === s ? styles.active : ''}`}
              style={sport === s ? { borderColor: SPORT_COLORS[s], color: SPORT_COLORS[s], background: SPORT_COLORS[s] + '22' } : {}}
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
          <select className={styles.yearSelect} value={year} onChange={e => setYear(e.target.value)}>
            <option value="">All years</option>
            {years.map(y => <option key={y} value={y}>{y}</option>)}
          </select>
        </div>
      </div>

      {loading && <div className={styles.status}><span className={styles.spinner} /> Loading…</div>}
      {error   && <div className={styles.error}>{error}</div>}

      {!loading && !error && (
        <>
          <div className={styles.grid}>
            {sets.map((s, i) => {
              const color = SPORT_COLORS[s.sport] ?? '#6c63ff'
              return (
                <button key={i} className={styles.setCard} onClick={() => goToSet(s)}>
                  {/* Box art — real image if available, gradient fallback */}
                  <BoxArt imageUrl={s.box_image_url} year={s.year} sport={s.sport} color={color} />

                  <div className={styles.cardBody}>
                    <div className={styles.setName}>{s.set_name}</div>
                    {s.brand && <div className={styles.brand}>{s.brand}</div>}
                    <div className={styles.stats}>
                      <span><strong>{s.total_cards?.toLocaleString()}</strong> cards</span>
                      <span><strong>{s.total_variants?.toLocaleString()}</strong> variants</span>
                      <span><strong>{s.total_players?.toLocaleString()}</strong> players</span>
                    </div>
                  </div>
                </button>
              )
            })}
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
