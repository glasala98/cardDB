import { useState, useEffect, useCallback, useRef } from 'react'
import { useSearchParams } from 'react-router-dom'
import { searchSales } from '../api/search'
import client from '../api/client'
import SearchBar from '../components/SearchBar'
import SearchFilters from '../components/SearchFilters'
import SearchResultRow from '../components/SearchResultRow'
import SaleDetailModal from '../components/SaleDetailModal'
import styles from './Search.module.css'

const PAGE_SIZE = 25
const DEBOUNCE_MS = 350

function paramsToFilters(sp) {
  return {
    sources:     sp.getAll('source'),
    sort:        sp.get('sort') ?? 'date_desc',
    price_min:   sp.get('price_min') ?? undefined,
    price_max:   sp.get('price_max') ?? undefined,
    date_from:   sp.get('date_from') ?? undefined,
    date_to:     sp.get('date_to') ?? undefined,
    graded_only: sp.get('graded_only') === '1' ? true : undefined,
  }
}

function filtersToParams(q, filters, page) {
  const p = new URLSearchParams()
  if (q) p.set('q', q)
  if (filters.sort && filters.sort !== 'date_desc') p.set('sort', filters.sort)
  ;(filters.sources ?? []).forEach(s => p.append('source', s))
  if (filters.price_min) p.set('price_min', filters.price_min)
  if (filters.price_max) p.set('price_max', filters.price_max)
  if (filters.date_from) p.set('date_from', filters.date_from)
  if (filters.date_to)   p.set('date_to',   filters.date_to)
  if (filters.graded_only) p.set('graded_only', '1')
  if (page > 1) p.set('page', String(page))
  return p
}

export default function Search() {
  const [searchParams, setSearchParams] = useSearchParams()
  const [query,   setQuery]   = useState(searchParams.get('q') ?? '')
  const [filters, setFilters] = useState(() => paramsToFilters(searchParams))
  const [page,    setPage]    = useState(Number(searchParams.get('page') ?? 1))

  // null = idle (never searched), [] = searched + empty, [...] = has results
  const [results, setResults] = useState(null)
  const [total,   setTotal]   = useState(null)
  const [loading, setLoading] = useState(false)
  const [error,   setError]   = useState(null)

  const [selectedSale, setSelectedSale] = useState(null)
  const [trending,     setTrending]     = useState([])

  const debounceRef = useRef(null)
  const reqIdRef    = useRef(0)   // increments on each search; stale responses are ignored

  useEffect(() => {
    client.get('/search/trending').then(d => setTrending(d ?? [])).catch(() => {})
  }, [])

  // Debounced search — fires 350ms after query/filters/page settle
  useEffect(() => {
    clearTimeout(debounceRef.current)

    if (!query.trim() || query.trim().length < 2) {
      setResults(null)
      setTotal(null)
      setError(null)
      setLoading(false)
      return
    }

    debounceRef.current = setTimeout(() => {
      runSearch(query, filters, page)
    }, DEBOUNCE_MS)

    return () => clearTimeout(debounceRef.current)
  }, [query, filters, page])  // eslint-disable-line

  async function runSearch(q, f, pg) {
    const myId = ++reqIdRef.current
    setLoading(true)
    setError(null)

    const urlParams = new URLSearchParams()
    urlParams.set('q',      q.trim())
    urlParams.set('sort',   f.sort ?? 'date_desc')
    urlParams.set('limit',  String(PAGE_SIZE))
    urlParams.set('offset', String((pg - 1) * PAGE_SIZE))
    ;(f.sources ?? []).forEach(s => urlParams.append('source', s))
    if (f.price_min)   urlParams.set('price_min',   f.price_min)
    if (f.price_max)   urlParams.set('price_max',   f.price_max)
    if (f.date_from)   urlParams.set('date_from',   f.date_from)
    if (f.date_to)     urlParams.set('date_to',     f.date_to)
    if (f.graded_only) urlParams.set('graded_only', '1')

    setSearchParams(filtersToParams(q, f, pg), { replace: true })

    try {
      const data = await searchSales(Object.fromEntries(urlParams))
      // Ignore stale responses from previous keystrokes
      if (myId !== reqIdRef.current) return
      setResults(data.results ?? [])
      setTotal(data.total ?? 0)
    } catch (e) {
      if (myId !== reqIdRef.current) return
      const msg = e?.message || 'Search failed — please try again.'
      setError(msg)
      setResults([])  // show body section so error is visible
    } finally {
      if (myId === reqIdRef.current) setLoading(false)
    }
  }

  function handleQueryChange(q) { setQuery(q); setPage(1) }
  function handleFiltersChange(f) { setFilters(f); setPage(1) }
  function handleSubmit(q) {
    clearTimeout(debounceRef.current)
    setQuery(q)
    setPage(1)
    if (q.trim().length >= 2) runSearch(q, filters, 1)
  }

  const totalPages = total != null ? Math.ceil(total / PAGE_SIZE) : 0
  const hasSearched = results !== null

  return (
    <div className={styles.page}>
      <div className={styles.hero}>
        <h1 className={styles.heading}>Card Sales Search</h1>
        <p className={styles.sub}>Every sale. Every source. No paywalls.</p>
        <div className={styles.searchWrap}>
          <SearchBar
            value={query}
            onChange={handleQueryChange}
            onSubmit={handleSubmit}
            placeholder="Search by player, set, year, grade…"
          />
        </div>
      </div>

      {hasSearched && (
        <div className={styles.body}>
          <div className={styles.filtersWrap}>
            <SearchFilters
              filters={filters}
              onChange={handleFiltersChange}
              totalCount={total}
            />
          </div>

          {loading && (
            <div className={styles.statusRow}>
              <span className={styles.spinner} />
              <span>Searching…</span>
            </div>
          )}

          {error && !loading && (
            <div className={styles.error}>{error}</div>
          )}

          {!loading && !error && results?.length === 0 && (
            <div className={styles.empty}>
              <p>No sales found for <strong>"{query}"</strong></p>
              <p className={styles.emptySub}>Try a shorter query or broaden your filters.</p>
            </div>
          )}

          {!loading && results?.length > 0 && (
            <>
              <div className={styles.resultList}>
                {results.map((sale, i) => (
                  <SearchResultRow
                    key={sale.id ?? i}
                    sale={sale}
                    onClick={() => setSelectedSale(sale)}
                  />
                ))}
              </div>

              {totalPages > 1 && (
                <div className={styles.pagination}>
                  <button
                    className={styles.pageBtn}
                    disabled={page <= 1}
                    onClick={() => setPage(p => p - 1)}
                  >← Prev</button>
                  <span className={styles.pageInfo}>Page {page} of {totalPages}</span>
                  <button
                    className={styles.pageBtn}
                    disabled={page >= totalPages}
                    onClick={() => setPage(p => p + 1)}
                  >Next →</button>
                </div>
              )}
            </>
          )}
        </div>
      )}

      {!hasSearched && !loading && (
        <div className={styles.prompt}>
          <p>Search across eBay, Goldin, Heritage, PWCC, Fanatics, Pristine, and MySlabs.</p>
          {trending.length > 0 && (
            <div className={styles.trending}>
              <span className={styles.trendLabel}>Trending:</span>
              {trending.slice(0, 8).map((t, i) => (
                <button
                  key={i}
                  className={styles.trendChip}
                  onClick={() => handleSubmit(t.query)}
                >
                  {t.query}
                </button>
              ))}
            </div>
          )}
        </div>
      )}

      {selectedSale && (
        <SaleDetailModal sale={selectedSale} onClose={() => setSelectedSale(null)} />
      )}
    </div>
  )
}
