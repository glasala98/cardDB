import { useState, useEffect, useCallback, useRef } from 'react'
import { useSearchParams } from 'react-router-dom'
import { searchSales } from '../api/search'
import SearchBar from '../components/SearchBar'
import SearchFilters from '../components/SearchFilters'
import SearchResultRow from '../components/SearchResultRow'
import styles from './Search.module.css'

const PAGE_SIZE = 25

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
  const [query, setQuery] = useState(searchParams.get('q') ?? '')
  const [filters, setFilters] = useState(() => paramsToFilters(searchParams))
  const [page, setPage] = useState(Number(searchParams.get('page') ?? 1))
  const [results, setResults] = useState(null)   // null = idle, [] = empty
  const [total, setTotal] = useState(null)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState(null)
  const abortRef = useRef(null)

  const doSearch = useCallback(async (q, f, pg) => {
    if (!q.trim()) { setResults(null); setTotal(null); return }
    abortRef.current?.abort()
    abortRef.current = new AbortController()
    setLoading(true); setError(null)
    try {
      const params = {
        q: q.trim(),
        sort: f.sort ?? 'date_desc',
        limit: PAGE_SIZE,
        offset: (pg - 1) * PAGE_SIZE,
      }
      ;(f.sources ?? []).forEach((s, i) => { params[`source`] = s })  // handled below
      const sources = f.sources ?? []
      if (f.price_min) params.price_min = f.price_min
      if (f.price_max) params.price_max = f.price_max
      if (f.date_from) params.date_from = f.date_from
      if (f.date_to)   params.date_to   = f.date_to
      if (f.graded_only) params.graded_only = '1'

      // Build full URL params with repeated source= keys
      const urlParams = new URLSearchParams()
      Object.entries(params).forEach(([k, v]) => { if (k !== 'source') urlParams.set(k, v) })
      sources.forEach(s => urlParams.append('source', s))

      const data = await searchSales(Object.fromEntries(urlParams))
      setResults(data.results ?? [])
      setTotal(data.total ?? 0)
    } catch (e) {
      if (e?.name !== 'CanceledError') setError('Search failed. Try again.')
    } finally { setLoading(false) }
  }, [])

  // Sync URL + trigger search on query/filter/page change
  useEffect(() => {
    setSearchParams(filtersToParams(query, filters, page), { replace: true })
    doSearch(query, filters, page)
  }, [query, filters, page]) // eslint-disable-line

  function handleQueryChange(q) { setQuery(q); setPage(1) }
  function handleFiltersChange(f) { setFilters(f); setPage(1) }
  function handleSubmit(q) { setQuery(q); setPage(1) }

  const totalPages = total != null ? Math.ceil(total / PAGE_SIZE) : 0

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

      {(results !== null || loading) && (
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

          {error && <div className={styles.error}>{error}</div>}

          {!loading && results?.length === 0 && (
            <div className={styles.empty}>
              <p>No sales found for <strong>"{query}"</strong></p>
              <p className={styles.emptySub}>Try a shorter query or remove filters.</p>
            </div>
          )}

          {!loading && results?.length > 0 && (
            <>
              <div className={styles.resultList}>
                {results.map((sale, i) => (
                  <SearchResultRow key={sale.id ?? i} sale={sale} />
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

      {results === null && !loading && (
        <div className={styles.prompt}>
          <p>Search across eBay, Goldin, Heritage, PWCC, Fanatics, Pristine, and MySlabs.</p>
        </div>
      )}
    </div>
  )
}
