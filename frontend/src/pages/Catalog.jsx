import { useState, useEffect, useCallback, useRef, useLayoutEffect } from 'react'
import CardTable from '../components/CardTable'
import { getCatalog, getCatalogFilters } from '../api/catalog'
import { useCurrency } from '../context/CurrencyContext'
import CurrencySelect from '../components/CurrencySelect'
import styles from './Catalog.module.css'
import pageStyles from './Page.module.css'

const SPORTS = ['NHL', 'NBA', 'NFL', 'MLB']

const COLUMNS = (fmtPrice) => [
  { key: 'sport',       label: 'Sport' },
  { key: 'year',        label: 'Year',       render: v => v || '—' },
  { key: 'set_name',    label: 'Set',        render: v => v || '—' },
  { key: 'card_number', label: '#',          render: v => v || '—' },
  { key: 'player_name', label: 'Player' },
  { key: 'team',        label: 'Team',       render: v => v || '—' },
  { key: 'variant',     label: 'Variant',    render: v => v || '—' },
  {
    key: 'is_rookie',
    label: 'RC',
    render: v => v ? <span className={styles.rcBadge}>RC</span> : null,
  },
  {
    key: 'fair_value',
    label: 'Price',
    render: (v, row) => v != null
      ? <span className={styles.price}>{fmtPrice(v)}</span>
      : <span className={styles.noPrice}>—</span>,
  },
  {
    key: 'trend',
    label: 'Trend',
    render: v => {
      if (!v || v === 'no data') return <span className={styles.trendFlat}>—</span>
      if (v === 'up')   return <span className={styles.trendUp}>▲ up</span>
      if (v === 'down') return <span className={styles.trendDown}>▼ down</span>
      return <span className={styles.trendFlat}>{v}</span>
    },
  },
  {
    key: 'confidence',
    label: 'Conf.',
    render: v => v
      ? <span className={`${styles.conf} ${styles['conf_' + (v || 'none').replace(' ', '_')]}`}>{v}</span>
      : null,
  },
  { key: 'num_sales', label: 'Sales', render: v => v ?? '—' },
]

const PER_PAGE = 50

export default function Catalog() {
  const { fmtPrice } = useCurrency()

  const [cards,     setCards]     = useState([])
  const [total,     setTotal]     = useState(0)
  const [pages,     setPages]     = useState(1)
  const [page,      setPage]      = useState(1)
  const [loading,   setLoading]   = useState(false)
  const [error,     setError]     = useState(null)

  // Filters
  const [search,   setSearch]   = useState('')
  const [sport,    setSport]    = useState('')
  const [year,     setYear]     = useState('')
  const [setName,  setSetName]  = useState('')
  // Sort
  const [sortKey, setSortKey] = useState('year')
  const [sortDir, setSortDir] = useState('desc')

  // Filter options
  const [years, setYears] = useState([])
  const [sets,  setSets]  = useState([])

  const searchTimer = useRef(null)
  const [showTip, setShowTip] = useState(false)
  useLayoutEffect(() => {
    setShowTip(localStorage.getItem('catalog_tip_dismissed') !== '1')
  }, [])

  // Reload years when sport changes; reset dependent filters
  useEffect(() => {
    setYear('')
    setSetName('')
    setYears([])
    setSets([])
    if (!sport) return
    getCatalogFilters(sport, null)
      .then(data => setYears(data.years || []))
      .catch(() => {})
  }, [sport])

  // Reload sets when year changes
  useEffect(() => {
    if (!year) return
    getCatalogFilters(sport || null, year)
      .then(data => setSets(data.sets || []))
      .catch(() => {})
    setSetName('')
  }, [year]) // eslint-disable-line react-hooks/exhaustive-deps

  const fetchPage = useCallback((pg, overrides = {}) => {
    setLoading(true)
    setError(null)
    const params = {
      page:     pg,
      per_page: PER_PAGE,
      sort:     sortKey,
      dir:      sortDir,
      ...(search   && { search }),
      ...(sport    && { sport }),
      ...(year     && { year }),
      ...(setName  && { set_name: setName }),
...overrides,
    }
    getCatalog(params)
      .then(data => {
        setCards(data.cards   || [])
        setTotal(data.total   || 0)
        setPages(data.pages   || 1)
        setPage(data.page     || 1)
      })
      .catch(e => setError(e.message))
      .finally(() => setLoading(false))
  }, [search, sport, year, setName, sortKey, sortDir])

  // Re-fetch on filter/sort change (debounce search)
  useEffect(() => {
    clearTimeout(searchTimer.current)
    searchTimer.current = setTimeout(() => {
      setPage(1)
      fetchPage(1)
    }, search ? 350 : 0)
    return () => clearTimeout(searchTimer.current)
  }, [search, sport, year, setName, sortKey, sortDir]) // eslint-disable-line react-hooks/exhaustive-deps

  const handleSort = (key) => {
    if (sortKey === key) setSortDir(d => d === 'asc' ? 'desc' : 'asc')
    else { setSortKey(key); setSortDir('desc') }
  }

  const goTo = (pg) => {
    if (pg < 1 || pg > pages) return
    setPage(pg)
    fetchPage(pg)
  }

  const clearFilters = () => {
    setSearch('')
    setSport('')
    setYear('')
    setSetName('')
setSortKey('year')
    setSortDir('desc')
  }

  const hasFilters = search || sport || year || setName

  return (
    <div className={pageStyles.page}>
      {/* Header */}
      <div className={pageStyles.header}>
        <h1 className={pageStyles.title}>Card Catalog</h1>
        <span className={pageStyles.count}>
          {total.toLocaleString()} cards
        </span>
        <div style={{ marginLeft: 'auto' }}>
          <CurrencySelect />
        </div>
      </div>

      {/* Sport tabs */}
      <div className={styles.sportTabs}>
        {['', ...SPORTS].map(s => (
          <button
            key={s || 'all'}
            className={`${styles.tab} ${sport === s ? styles.tabActive : ''}`}
            onClick={() => { setSport(s); setYear(''); setSetName('') }}
          >
            {s || 'All Sports'}
          </button>
        ))}
      </div>

      {/* Filters */}
      <div className={pageStyles.toolbar}>
        <input
          className={pageStyles.search}
          placeholder="Search player or set..."
          value={search}
          onChange={e => setSearch(e.target.value)}
        />

        <select
          className={pageStyles.filterSelect}
          value={year}
          onChange={e => setYear(e.target.value)}
        >
          <option value="">All Years</option>
          {years.map(y => <option key={y} value={y}>{y}</option>)}
        </select>

        <select
          className={pageStyles.filterSelect}
          value={setName}
          onChange={e => setSetName(e.target.value)}
          style={{ maxWidth: 200 }}
        >
          <option value="">All Sets</option>
          {sets.map(s => (
            <option key={s} value={s} title={s}>
              {s.length > 30 ? s.slice(0, 28) + '…' : s}
            </option>
          ))}
        </select>

        {hasFilters && (
          <button className={pageStyles.clearBtn} onClick={clearFilters}>
            Clear Filters
          </button>
        )}
      </div>

      {/* Tips */}
      {showTip && (
        <div className={styles.tipBar}>
          <span className={styles.tipIcon}>💡</span>
          <span className={styles.tipText}>
            <strong>Navigating the catalog:</strong> Pick a sport tab, then narrow by Year and Set.
            The Year and Set dropdowns update based on your sport selection.
            Use the search box to find any player or set name across the entire catalog.
            Click any column header to sort.
          </span>
          <button
            className={styles.tipClose}
            onClick={() => { localStorage.setItem('catalog_tip_dismissed', '1'); setShowTip(false) }}
            title="Dismiss"
          >✕</button>
        </div>
      )}

      {error && <div className={pageStyles.error}>{error}</div>}

      {/* Table */}
      {loading && cards.length === 0 ? (
        <div className={pageStyles.status}>Loading...</div>
      ) : (
        <>
          <CardTable
            columns={COLUMNS(fmtPrice)}
            rows={cards}
            sortKey={sortKey}
            sortDir={sortDir}
            onSort={handleSort}
          />

          {loading && <div className={styles.loadingBar} />}

          {/* Pagination */}
          {pages > 1 && (
            <div className={styles.pagination}>
              <button
                className={styles.pgBtn}
                onClick={() => goTo(1)}
                disabled={page === 1}
              >«</button>
              <button
                className={styles.pgBtn}
                onClick={() => goTo(page - 1)}
                disabled={page === 1}
              >‹</button>

              {buildPageRange(page, pages).map((p, i) =>
                p === '...'
                  ? <span key={`ellipsis-${i}`} className={styles.pgEllipsis}>…</span>
                  : <button
                      key={p}
                      className={`${styles.pgBtn} ${p === page ? styles.pgActive : ''}`}
                      onClick={() => goTo(p)}
                    >{p}</button>
              )}

              <button
                className={styles.pgBtn}
                onClick={() => goTo(page + 1)}
                disabled={page === pages}
              >›</button>
              <button
                className={styles.pgBtn}
                onClick={() => goTo(pages)}
                disabled={page === pages}
              >»</button>

              <span className={styles.pgInfo}>
                Page {page} of {pages.toLocaleString()} &nbsp;·&nbsp; {total.toLocaleString()} results
              </span>
            </div>
          )}
        </>
      )}
    </div>
  )
}

function buildPageRange(current, total) {
  if (total <= 7) return Array.from({ length: total }, (_, i) => i + 1)
  const pages = []
  pages.push(1)
  if (current > 3) pages.push('...')
  for (let p = Math.max(2, current - 1); p <= Math.min(total - 1, current + 1); p++) {
    pages.push(p)
  }
  if (current < total - 2) pages.push('...')
  pages.push(total)
  return pages
}
