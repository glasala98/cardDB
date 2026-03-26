import { useState, useEffect, useCallback, useRef } from 'react'
import { useNavigate, useLocation } from 'react-router-dom'
import { getCatalog, getCatalogFilters, getCatalogCardHistory, aiSearchCatalog, suggestPlayers } from '../api/catalog'
import { getOwnedIds, addToCollection, getGrades } from '../api/collection'
import { useCurrency } from '../context/CurrencyContext'
import { useAuth } from '../context/AuthContext'
import PageTabs from '../components/PageTabs'
import CatalogCardDetail from '../components/CatalogCardDetail'
import ImageLightbox from '../components/ImageLightbox'
import styles from './Catalog.module.css'
import pageStyles from './Page.module.css'

const CATALOG_TABS = [
  { to: '/catalog',    label: 'Browse'        },
  { to: '/collection', label: 'My Collection' },
]

const SPORTS = ['NHL', 'NBA', 'NFL', 'MLB']

const TIER_LABELS = { staple: 'Staple', premium: 'Premium', stars: 'Stars' }

const SPORT_COLORS = {
  NHL: { bg: '#0c2d54', text: '#4a9eff' },
  NBA: { bg: '#4a1500', text: '#ff6b35' },
  NFL: { bg: '#0a3318', text: '#3dba5e' },
  MLB: { bg: '#3d0a0a', text: '#e05555' },
}

// Optional columns that the user can toggle
const OPTIONAL_COLS = [
  { key: 'team',       label: 'Team'       },
  { key: 'confidence', label: 'Confidence' },
  { key: 'num_sales',  label: 'Sales'      },
  { key: 'variant',    label: 'Variant'    },
]
const DEFAULT_VISIBLE = { team: false, confidence: true, num_sales: true, variant: false }

function loadColPrefs() {
  try {
    const saved = localStorage.getItem('catalog_cols')
    return saved ? { ...DEFAULT_VISIBLE, ...JSON.parse(saved) } : DEFAULT_VISIBLE
  } catch { return DEFAULT_VISIBLE }
}

function CardThumb({ sport, playerName, imageUrl, hasImage }) {
  const colors = SPORT_COLORS[sport] || { bg: '#1e1e2e', text: '#888' }
  const initials = playerName
    ? playerName.split(' ').filter(Boolean).map(p => p[0]).slice(0, 2).join('').toUpperCase()
    : '?'
  if (imageUrl) {
    return (
      <div className={styles.cardThumb} style={hasImage ? { cursor: 'zoom-in' } : {}}>
        <img src={imageUrl} alt={playerName} className={styles.cardThumbImg} />
      </div>
    )
  }
  return (
    <div className={styles.cardThumb} style={{ background: colors.bg, borderColor: colors.text + '22' }}>
      <span className={styles.cardThumbInitials} style={{ color: colors.text }}>{initials}</span>
      <span className={styles.cardThumbSport} style={{ color: colors.text + 'aa' }}>{sport}</span>
    </div>
  )
}

const PER_PAGE = 25

export default function Catalog() {
  const { fmtPrice } = useCurrency()
  const { user } = useAuth()
  const navigate = useNavigate()
  const location = useLocation()
  const isLoggedIn = !!user

  const [cards,     setCards]     = useState([])
  const [total,     setTotal]     = useState(0)
  const [pages,     setPages]     = useState(1)
  const [page,      setPage]      = useState(1)
  const [loading,   setLoading]   = useState(false)
  const [error,     setError]     = useState(null)

  // Filters
  const [search,      setSearch]      = useState('')
  const [sport,       setSport]       = useState('')
  const [year,        setYear]        = useState('')
  const [setName,     setSetName]     = useState('')
  const [tierFilter,  setTierFilter]  = useState('')
  const [rcOnly,      setRcOnly]      = useState(false)
  const [showFilters, setShowFilters] = useState(false)

  // Sort
  const [sortKey, setSortKey] = useState('featured')
  const [sortDir, setSortDir] = useState('desc')

  // Quick filters
  const [hasPriceFilter, setHasPriceFilter] = useState(false)

  // Filter options
  const [years, setYears] = useState([])
  const [sets,  setSets]  = useState([])

  // Column visibility
  const [visibleCols, setVisibleCols] = useState(loadColPrefs)

  // Collection: owned card IDs + add-to-collection modal
  const [ownedIds,  setOwnedIds]  = useState(new Set())
  const [grades,    setGrades]    = useState([])
  const [addTarget, setAddTarget] = useState(null)
  const [addForm,   setAddForm]   = useState({ grade: 'Raw', quantity: '1', cost_basis: '', purchase_date: '' })
  const [addSaving, setAddSaving] = useState(false)

  // AI search
  const [aiQuery,    setAiQuery]    = useState('')
  const [aiLoading,  setAiLoading]  = useState(false)
  const [aiFilters,  setAiFilters]  = useState(null)
  const [aiMode,     setAiMode]     = useState(false)

  // Autocomplete
  const [suggestions,     setSuggestions]     = useState([])
  const [showSuggestions, setShowSuggestions] = useState(false)
  const searchRef = useRef(null)

  // Card detail panel
  const [detailCard,    setDetailCard]    = useState(null)
  const [detailHistory, setDetailHistory] = useState([])
  const [detailLoading, setDetailLoading] = useState(false)

  // Lightbox
  const [lightboxSrc,  setLightboxSrc]  = useState(null)
  const [lightboxAlt,  setLightboxAlt]  = useState('')

  useEffect(() => {
    document.title = 'Sports Card Prices & Market Values | CardDB'
    const metaDesc = document.querySelector('meta[name="description"]')
    if (metaDesc) metaDesc.setAttribute('content',
      'Free sports card price database. Search NHL, NBA, NFL, and MLB card values with recent eBay sales history and market trends.')
  }, [])

  // Pick up AI search result passed from the home page
  useEffect(() => {
    const params = new URLSearchParams(location.search)
    if (params.get('ai') !== '1') return
    const stored = sessionStorage.getItem('aiHomeResult')
    if (!stored) return
    sessionStorage.removeItem('aiHomeResult')
    try {
      const data = JSON.parse(stored)
      setAiQuery(data.query || '')
      setCards(data.cards || [])
      setTotal(data.total || 0)
      setPages(data.pages || 1)
      setAiFilters(data.filters || {})
      setAiMode(true)
    } catch (_) {}
  }, [location.search]) // eslint-disable-line react-hooks/exhaustive-deps

  useEffect(() => {
    if (!isLoggedIn) return
    getOwnedIds().then(d => setOwnedIds(new Set(d.owned_ids || []))).catch(() => {})
    getGrades().then(d => setGrades(d.grades || [])).catch(() => {})
  }, [isLoggedIn])

  const toggleCol = (key) => {
    setVisibleCols(prev => {
      const next = { ...prev, [key]: !prev[key] }
      localStorage.setItem('catalog_cols', JSON.stringify(next))
      return next
    })
  }

  const handleRowClick = (row) => {
    setDetailCard(row)
    setDetailHistory([])
    setDetailLoading(true)
    getCatalogCardHistory(row.id)
      .then(data => {
        setDetailCard(data.card)
        setDetailHistory(data.history || [])
      })
      .catch(() => {})
      .finally(() => setDetailLoading(false))
  }

  const handleAdd = (row) => {
    if (!isLoggedIn) { navigate('/login'); return }
    setAddTarget(row)
    setAddForm({ grade: 'Raw', quantity: '1', cost_basis: '', purchase_date: '' })
  }

  const submitAdd = async () => {
    if (!addTarget) return
    setAddSaving(true)
    try {
      await addToCollection({
        card_catalog_id: addTarget.id,
        grade:           addForm.grade,
        quantity:        parseInt(addForm.quantity) || 1,
        cost_basis:      addForm.cost_basis ? parseFloat(addForm.cost_basis) : null,
        purchase_date:   addForm.purchase_date || null,
      })
      setOwnedIds(prev => new Set([...prev, addTarget.id]))
      setAddTarget(null)
    } catch (e) {
      alert(e.message)
    } finally {
      setAddSaving(false)
    }
  }

  const searchTimer = useRef(null)

  // Reload years when sport or search changes
  useEffect(() => {
    setYear('')
    setSetName('')
    setSets([])
    // Need at least a sport or a meaningful search term to scope years
    const q = search.length >= 2 ? search : null
    if (!sport && !q) { setYears([]); return }
    getCatalogFilters(sport || null, null, q)
      .then(data => setYears(data.years || []))
      .catch(() => {})
  }, [sport, search]) // eslint-disable-line react-hooks/exhaustive-deps

  // Reload sets when year changes (also scoped to current search)
  useEffect(() => {
    if (!year) return
    const q = search.length >= 2 ? search : null
    getCatalogFilters(sport || null, year, q)
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
      ...(search          && { search }),
      ...(sport           && { sport }),
      ...(year            && { year }),
      ...(setName         && { set_name: setName }),
      ...(tierFilter      && { tier: tierFilter }),
      ...(rcOnly          && { is_rookie: true }),
      ...(hasPriceFilter  && { has_price: true }),
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
  }, [search, sport, year, setName, tierFilter, rcOnly, hasPriceFilter, sortKey, sortDir])

  useEffect(() => {
    clearTimeout(searchTimer.current)
    searchTimer.current = setTimeout(() => {
      setPage(1)
      fetchPage(1)
    }, search ? 350 : 0)
    return () => clearTimeout(searchTimer.current)
  }, [search, sport, year, setName, tierFilter, rcOnly, hasPriceFilter, sortKey, sortDir]) // eslint-disable-line react-hooks/exhaustive-deps

  // Fetch autocomplete suggestions when search input changes
  useEffect(() => {
    if (search.length < 2) { setSuggestions([]); setShowSuggestions(false); return }
    const t = setTimeout(() => {
      suggestPlayers(search, sport || null)
        .then(data => { setSuggestions(data || []); setShowSuggestions((data || []).length > 0) })
        .catch(() => setSuggestions([]))
    }, 200)
    return () => clearTimeout(t)
  }, [search, sport])

  // Dismiss suggestions on click-outside
  useEffect(() => {
    const handler = (e) => { if (searchRef.current && !searchRef.current.contains(e.target)) setShowSuggestions(false) }
    document.addEventListener('mousedown', handler)
    return () => document.removeEventListener('mousedown', handler)
  }, [])

  const handleSort = (key) => {
    if (key === 'featured') { setSortKey('featured'); setSortDir('desc'); return }
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
    setTierFilter('')
    setRcOnly(false)
    setHasPriceFilter(false)
    setSortKey('featured')
    setSortDir('desc')
  }

  const handleAiSearch = (e) => {
    e.preventDefault()
    if (!aiQuery.trim()) return
    setAiLoading(true)
    setAiMode(false)
    setAiFilters(null)
    aiSearchCatalog(aiQuery.trim())
      .then(data => {
        setCards(data.cards || [])
        setTotal(data.total || 0)
        setPages(data.pages || 1)
        setPage(1)
        setAiFilters(data.filters || {})
        setAiMode(true)
      })
      .catch(e => setError(e.message))
      .finally(() => setAiLoading(false))
  }

  const clearAiSearch = () => {
    setAiQuery('')
    setAiMode(false)
    setAiFilters(null)
    fetchPage(1)
  }

  const hasFilters = !!(search || sport || year || setName || tierFilter || rcOnly || hasPriceFilter)

  return (
    <div className={pageStyles.page}>
      <PageTabs tabs={CATALOG_TABS} />

      {/* ── Top bar ─────────────────────────────────────────────── */}
      <div className={styles.topBar}>
        <div className={styles.topBarLeft}>
          <h1 className={styles.pageTitle}>Card Catalog</h1>
          <span className={styles.countBadge}>
            {hasFilters ? `${total.toLocaleString()} results` : `${total.toLocaleString()} cards`}
          </span>
          <button
            className={`${styles.filterToggleBtn} ${hasFilters ? styles.filterToggleActive : ''}`}
            onClick={() => setShowFilters(true)}
          >
            ⚙ Filters{hasFilters ? ' (on)' : ''}
          </button>
        </div>
      </div>

      {/* ── Layout: sidebar + main ───────────────────────────────── */}
      <div className={styles.layout}>

        {/* Mobile overlay */}
        {showFilters && (
          <div className={styles.drawerOverlay} onClick={() => setShowFilters(false)} />
        )}

        {/* Filter sidebar */}
        <aside className={`${styles.filterPanel} ${showFilters ? styles.drawerOpen : ''}`}>

          <div className={styles.drawerHeader}>
            <span className={styles.drawerTitle}>Filters</span>
            <button className={styles.drawerClose} onClick={() => setShowFilters(false)}>✕</button>
          </div>

          <div className={styles.filterSection} ref={searchRef} style={{ position: 'relative' }}>
            <input
              className={styles.sideSearch}
              placeholder="Player or set…"
              value={search}
              onChange={e => { setSearch(e.target.value); setShowSuggestions(true) }}
              onFocus={() => suggestions.length > 0 && setShowSuggestions(true)}
            />
            {showSuggestions && suggestions.length > 0 && (
              <ul className={styles.suggestions}>
                {suggestions.map((s, i) => s.type === 'player' ? (
                  <li
                    key={`p-${s.player_name}-${i}`}
                    className={styles.suggestionItem}
                    onMouseDown={() => { setSearch(s.player_name); setShowSuggestions(false) }}
                  >
                    <span>{s.player_name}</span>
                    <span className={styles.suggestionCount}>{s.count}</span>
                  </li>
                ) : (
                  <li
                    key={`c-${s.id}`}
                    className={`${styles.suggestionItem} ${styles.suggestionCard}`}
                    onMouseDown={() => { setShowSuggestions(false); navigate(`/catalog/${s.id}`) }}
                  >
                    <span className={styles.suggestionCardLabel}>
                      {s.year} {s.set_name}{s.variant ? ` · ${s.variant}` : ''}
                      {s.is_rookie && <span className={styles.rcBadge}>RC</span>}
                    </span>
                    {s.num_sales != null && (
                      <span className={styles.suggestionCount}>{s.num_sales} sales</span>
                    )}
                  </li>
                ))}
              </ul>
            )}
          </div>

          <div className={styles.filterSection}>
            <span className={styles.filterLabel}>Sport</span>
            <div className={styles.sideBtnGrid}>
              {['', ...SPORTS].map(s => (
                <button
                  key={s || 'all'}
                  className={`${styles.sideBtn} ${sport === s ? styles.sideBtnActive : ''}`}
                  onClick={() => { setSport(s); setYear(''); setSetName('') }}
                >
                  {s || 'All'}
                </button>
              ))}
            </div>
          </div>

          <div className={styles.filterSection}>
            <span className={styles.filterLabel}>Year</span>
            <select
              className={styles.sideSelect}
              value={year}
              onChange={e => setYear(e.target.value)}
              disabled={!sport && search.length < 2}
            >
              <option value="">{sport || search.length >= 2 ? 'All Years' : 'Select sport first'}</option>
              {years.map(y => <option key={y} value={y}>{y}</option>)}
            </select>
          </div>

          <div className={styles.filterSection}>
            <span className={styles.filterLabel}>Set</span>
            <select className={styles.sideSelect} value={setName} onChange={e => setSetName(e.target.value)}>
              <option value="">All Sets</option>
              {sets.map(s => (
                <option key={s} value={s}>{s.length > 30 ? s.slice(0, 28) + '…' : s}</option>
              ))}
            </select>
          </div>

          <div className={styles.filterSection}>
            <span className={styles.filterLabel}>Tier</span>
            <div className={styles.sideBtnGrid}>
              {[['', 'All'], ['staple', 'Staple'], ['premium', 'Prem'], ['stars', 'Stars']].map(([val, label]) => (
                <button
                  key={val || 'all'}
                  className={`${styles.sideBtn} ${tierFilter === val ? styles.sideBtnActive : ''}`}
                  onClick={() => setTierFilter(val)}
                >
                  {label}
                </button>
              ))}
            </div>
            <button
              className={`${styles.sideBtn} ${styles.sideBtnFull} ${rcOnly ? styles.sideBtnActive : ''}`}
              onClick={() => setRcOnly(v => !v)}
            >
              RC Only
            </button>
          </div>

          {hasFilters && (
            <div className={styles.filterSection}>
              <button className={styles.clearBtn} onClick={clearFilters}>Clear filters</button>
            </div>
          )}
        </aside>

        {/* ── Main area ──────────────────────────────────────────── */}
        <div className={styles.mainArea}>

          {/* Sport quick-tabs + Priced toggle */}
          <div className={styles.quickFilters}>
            <div className={styles.sportTabsMain}>
              {['', ...SPORTS].map(s => {
                const color = s ? SPORT_COLORS[s]?.text : null
                const isActive = sport === s
                return (
                  <button
                    key={s || 'all'}
                    className={`${styles.sportTabMain} ${isActive ? styles.sportTabMainActive : ''}`}
                    style={isActive && color ? { borderColor: color, color, background: color + '22' } : {}}
                    onClick={() => { setSport(s); setYear(''); setSetName('') }}
                  >{s || 'All'}</button>
                )
              })}
            </div>
            <button
              className={`${styles.pricedBtn} ${hasPriceFilter ? styles.pricedBtnActive : ''}`}
              onClick={() => setHasPriceFilter(v => !v)}
              title="Only show cards with a market price"
            >Priced</button>
          </div>

          {/* Active filter chips */}
          {hasFilters && !aiMode && (
            <div className={styles.filterChips}>
              {search && (
                <span className={styles.filterChip}>"{search}" <button onClick={() => setSearch('')}>×</button></span>
              )}
              {year && (
                <span className={styles.filterChip}>{year} <button onClick={() => setYear('')}>×</button></span>
              )}
              {setName && (
                <span className={styles.filterChip}>{setName.length > 22 ? setName.slice(0, 20) + '…' : setName} <button onClick={() => setSetName('')}>×</button></span>
              )}
              {tierFilter && (
                <span className={styles.filterChip}>{TIER_LABELS[tierFilter]} <button onClick={() => setTierFilter('')}>×</button></span>
              )}
              {rcOnly && (
                <span className={styles.filterChip}>RC Only <button onClick={() => setRcOnly(false)}>×</button></span>
              )}
              {hasPriceFilter && (
                <span className={styles.filterChip}>Priced <button onClick={() => setHasPriceFilter(false)}>×</button></span>
              )}
              <button className={styles.clearAllChip} onClick={clearFilters}>Clear all</button>
            </div>
          )}

          {/* AI search bar */}
          <form className={styles.aiSearchBar} onSubmit={handleAiSearch}>
            <span className={styles.aiIcon}>✦</span>
            <input
              className={styles.aiInput}
              placeholder='Ask AI — e.g. "Connor McDavid Young Guns under $200"'
              value={aiQuery}
              onChange={e => setAiQuery(e.target.value)}
              disabled={aiLoading}
            />
            <button type="submit" className={styles.aiBtn} disabled={aiLoading || !aiQuery.trim()}>
              {aiLoading ? 'Searching…' : 'Search'}
            </button>
            {aiMode && (
              <button type="button" className={styles.aiClearBtn} onClick={clearAiSearch}>
                ✕ Clear AI
              </button>
            )}
          </form>
          {aiMode && aiFilters && (
            <div className={styles.aiFilterBadges}>
              <span className={styles.aiBadgeLabel}>AI understood:</span>
              {Object.entries(aiFilters).map(([k, v]) =>
                v != null && v !== '' && v !== false ? (
                  <span key={k} className={styles.aiBadge}>
                    {k.replace(/_/g, ' ')}: <strong>{String(v)}</strong>
                  </span>
                ) : null
              )}
            </div>
          )}

          {error && <div className={pageStyles.error}>{error}</div>}

          {/* Column toggles */}
          <div className={styles.colToggleRow}>
            <span className={styles.colToggleLabel}>Columns:</span>
            {OPTIONAL_COLS.map(col => (
              <button
                key={col.key}
                className={`${styles.colToggleBtn} ${visibleCols[col.key] ? styles.colToggleBtnOn : ''}`}
                onClick={() => toggleCol(col.key)}
              >
                {col.label}
              </button>
            ))}
          </div>

          {/* Table */}
          {loading && cards.length === 0 ? (
            <div className={styles.tableWrap}>
              <table className={styles.table}>
                <thead>
                  <tr>
                    <th className={styles.th} style={{ width: 44 }} />
                    <th className={styles.th}>Card</th>
                    <th className={`${styles.th} ${styles.thRight}`}>Price</th>
                    <th className={styles.th} style={{ width: 72 }} />
                  </tr>
                </thead>
                <tbody>
                  {Array.from({ length: 12 }).map((_, i) => (
                    <tr key={i} className={styles.skeletonRow}>
                      <td className={styles.tdThumb}><div className={styles.skeletonThumb} /></td>
                      <td>
                        <div className={styles.cardCell}>
                          <div className={styles.skeletonBlock} style={{ width: `${120 + (i % 4) * 30}px`, height: 14 }} />
                          <div className={styles.skeletonBlock} style={{ width: `${80 + (i % 3) * 20}px`, height: 11, marginTop: 4 }} />
                        </div>
                      </td>
                      <td className={styles.tdRight}><div className={styles.skeletonBlock} style={{ width: 52, height: 14, marginLeft: 'auto' }} /></td>
                      <td className={styles.tdAction}><div className={styles.skeletonBlock} style={{ width: 44, height: 24, marginLeft: 'auto' }} /></td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          ) : cards.length === 0 ? (
            <div className={pageStyles.status}>No cards found.</div>
          ) : (
            <>
              <div className={styles.tableWrap}>
                <table className={styles.table}>
                  <thead>
                    <tr>
                      <th className={styles.th} style={{ width: 44 }} />
                      <th
                        className={`${styles.th} ${styles.sortable}`}
                        onClick={() => handleSort('player_name')}
                      >
                        Card
                        {sortKey === 'player_name' && <span className={styles.sortArrow}>{sortDir === 'asc' ? ' ↑' : ' ↓'}</span>}
                      </th>
                      {visibleCols.variant && <th className={styles.th}>Variant</th>}
                      {visibleCols.team    && <th className={styles.th}>Team</th>}
                      <th
                        className={`${styles.th} ${styles.sortable} ${styles.thRight}`}
                        onClick={() => handleSort('fair_value')}
                      >
                        Price
                        {sortKey === 'fair_value' && <span className={styles.sortArrow}>{sortDir === 'asc' ? ' ↑' : ' ↓'}</span>}
                      </th>
                      {visibleCols.confidence && <th className={`${styles.th} ${styles.hideMobile}`}>Conf.</th>}
                      {visibleCols.num_sales  && <th className={`${styles.th} ${styles.thRight} ${styles.hideMobile}`}>
                        <span
                          className={styles.sortable}
                          onClick={() => handleSort('num_sales')}
                        >
                          Sales{sortKey === 'num_sales' && <span className={styles.sortArrow}>{sortDir === 'asc' ? ' ↑' : ' ↓'}</span>}
                        </span>
                      </th>}
                      <th className={styles.th} style={{ width: 72 }}>
                        <span
                          className={`${styles.sortable} ${sortKey === 'featured' ? styles.featuredActive : styles.featuredInactive}`}
                          onClick={() => handleSort('featured')}
                          title="Sort by most desirable: tier + price + sales activity"
                        >
                          ✦{sortKey === 'featured' && <span className={styles.sortArrow}> on</span>}
                        </span>
                      </th>
                    </tr>
                  </thead>
                  <tbody>
                    {cards.map((row, i) => (
                      <tr
                        key={i}
                        className={styles.tr}
                        onClick={() => handleRowClick(row)}
                      >
                        {/* Thumbnail */}
                        <td
                          className={`${styles.td} ${styles.tdThumb}`}
                          onClick={row.image_url ? (e) => { e.stopPropagation(); setLightboxSrc(row.image_url); setLightboxAlt(row.player_name) } : undefined}
                        >
                          <CardThumb
                            sport={row.sport}
                            playerName={row.player_name}
                            imageUrl={row.image_url}
                            hasImage={!!row.image_url}
                          />
                        </td>

                        {/* Card info */}
                        <td className={styles.td}>
                          <div className={styles.cardCell}>
                            <div className={styles.cardPlayerRow}>
                              <span className={styles.playerPrimary}>{row.player_name}</span>
                              {row.is_rookie && <span className={styles.rcBadge}>RC</span>}
                              {row.scrape_tier && TIER_LABELS[row.scrape_tier] && (
                                <span className={`${styles.tierBadge} ${styles['tier_' + row.scrape_tier]}`}>
                                  {TIER_LABELS[row.scrape_tier]}
                                </span>
                              )}
                            </div>
                            <div className={styles.cardSub}>
                              {!sport && row.sport && (
                                <span className={`${styles.sportTag} ${styles['sport_' + row.sport]}`}>{row.sport}</span>
                              )}
                              {row.year}
                              {row.set_name ? ` · ${row.set_name}` : ''}
                              {row.card_number ? ` · #${row.card_number}` : ''}
                              {row.variant && row.variant !== 'Base' && (
                                <span className={styles.variantInline}>{row.variant}</span>
                              )}
                            </div>
                          </div>
                        </td>

                        {/* Optional: Variant */}
                        {visibleCols.variant && (
                          <td className={styles.td}>
                            <span className={styles.variantLabel}>
                              {row.variant && row.variant !== 'Base' ? row.variant : <span className={styles.muted}>Base</span>}
                            </span>
                          </td>
                        )}

                        {/* Optional: Team */}
                        {visibleCols.team && (
                          <td className={styles.td}>
                            <span className={styles.muted}>{row.team || '—'}</span>
                          </td>
                        )}

                        {/* Price + trend */}
                        <td className={`${styles.td} ${styles.tdRight}`}>
                          {row.fair_value != null ? (
                            <div className={styles.priceCell}>
                              <span className={styles.price}>{fmtPrice(row.fair_value)}</span>
                              {row.trend === 'up'   && <span className={styles.trendUp}>▲</span>}
                              {row.trend === 'down' && <span className={styles.trendDown}>▼</span>}
                            </div>
                          ) : (
                            <span className={styles.muted}>—</span>
                          )}
                        </td>

                        {/* Optional: Confidence */}
                        {visibleCols.confidence && (
                          <td className={`${styles.td} ${styles.hideMobile}`}>
                            {row.confidence
                              ? <span className={`${styles.conf} ${styles['conf_' + row.confidence]}`}>{row.confidence}</span>
                              : <span className={styles.muted}>—</span>
                            }
                          </td>
                        )}

                        {/* Optional: Sales */}
                        {visibleCols.num_sales && (
                          <td className={`${styles.td} ${styles.tdRight} ${styles.hideMobile}`}>
                            <span className={styles.muted}>{row.num_sales ?? '—'}</span>
                          </td>
                        )}

                        {/* Add / Owned */}
                        <td className={`${styles.td} ${styles.tdAction}`} onClick={e => e.stopPropagation()}>
                          {!isLoggedIn
                            ? <span className={styles.signInToAdd}>+ Add</span>
                            : ownedIds.has(row.id)
                              ? <span className={styles.ownedBadge}>✓ Owned</span>
                              : <button className={styles.addBtn} onClick={() => handleAdd(row)}>+ Add</button>
                          }
                          <button
                            className={styles.viewBtn}
                            title="Full card page"
                            onClick={e => { e.stopPropagation(); navigate(`/catalog/${row.id}`) }}
                          >↗</button>
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>

              {loading && <div className={styles.loadingBar} />}

              {/* Pagination */}
              {pages > 1 && (
                <div className={styles.pagination}>
                  <button className={styles.pgBtn} onClick={() => goTo(1)}        disabled={page === 1}>«</button>
                  <button className={styles.pgBtn} onClick={() => goTo(page - 1)} disabled={page === 1}>‹</button>

                  {buildPageRange(page, pages).map((p, i) =>
                    p === '...'
                      ? <span key={`e-${i}`} className={styles.pgEllipsis}>…</span>
                      : <button
                          key={p}
                          className={`${styles.pgBtn} ${p === page ? styles.pgActive : ''}`}
                          onClick={() => goTo(p)}
                        >{p}</button>
                  )}

                  <button className={styles.pgBtn} onClick={() => goTo(page + 1)} disabled={page === pages}>›</button>
                  <button className={styles.pgBtn} onClick={() => goTo(pages)}    disabled={page === pages}>»</button>
                  <span className={styles.pgInfo}>
                    Page {page} of {pages.toLocaleString()} &nbsp;·&nbsp; {total.toLocaleString()} results
                  </span>
                </div>
              )}
            </>
          )}
        </div>
      </div>

      {/* Card detail panel */}
      {detailCard && (
        <CatalogCardDetail
          card={detailCard}
          history={detailHistory}
          loading={detailLoading}
          isLoggedIn={isLoggedIn}
          isOwned={ownedIds.has(detailCard.id)}
          onAdd={() => { setDetailCard(null); handleAdd(detailCard) }}
          onClose={() => setDetailCard(null)}
        />
      )}

      {/* Image lightbox */}
      {lightboxSrc && (
        <ImageLightbox
          src={lightboxSrc}
          alt={lightboxAlt}
          onClose={() => setLightboxSrc(null)}
        />
      )}

      {/* Add to Collection modal */}
      {addTarget && (
        <div className={styles.modalOverlay} onClick={() => setAddTarget(null)}>
          <div className={styles.modal} onClick={e => e.stopPropagation()}>
            <div className={styles.modalHeader}>
              <span>Add to Collection</span>
              <button className={styles.modalClose} onClick={() => setAddTarget(null)}>✕</button>
            </div>
            <div className={styles.modalCard}>
              <strong>{addTarget.player_name}</strong>
              <span>{addTarget.year} · {addTarget.set_name}</span>
              {addTarget.card_number && <span>#{addTarget.card_number}</span>}
            </div>
            <div className={styles.modalFields}>
              <label>
                Grade
                <select
                  value={addForm.grade}
                  onChange={e => setAddForm(p => ({ ...p, grade: e.target.value }))}
                >
                  {grades.map(g => <option key={g} value={g}>{g}</option>)}
                </select>
              </label>
              <label>
                Qty
                <input
                  type="number" min="1"
                  value={addForm.quantity}
                  onChange={e => setAddForm(p => ({ ...p, quantity: e.target.value }))}
                />
              </label>
              <label>
                Cost Paid
                <input
                  type="number" step="0.01" placeholder="0.00"
                  value={addForm.cost_basis}
                  onChange={e => setAddForm(p => ({ ...p, cost_basis: e.target.value }))}
                />
              </label>
              <label>
                Purchase Date
                <input
                  type="date"
                  value={addForm.purchase_date}
                  onChange={e => setAddForm(p => ({ ...p, purchase_date: e.target.value }))}
                />
              </label>
            </div>
            <div className={styles.modalActions}>
              <button className={styles.modalCancel} onClick={() => setAddTarget(null)}>Cancel</button>
              <button className={styles.modalSave} onClick={submitAdd} disabled={addSaving}>
                {addSaving ? 'Adding…' : 'Add to Collection'}
              </button>
            </div>
          </div>
        </div>
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
