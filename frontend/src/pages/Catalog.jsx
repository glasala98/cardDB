import { useState, useEffect, useCallback, useRef, useLayoutEffect } from 'react'
import { useNavigate } from 'react-router-dom'
import { getCatalog, getCatalogFilters, getCatalogCardHistory } from '../api/catalog'
import { getOwnedIds, addToCollection, getGrades } from '../api/collection'
import { useCurrency } from '../context/CurrencyContext'
import { useAuth } from '../context/AuthContext'
import PageTabs from '../components/PageTabs'
import CatalogCardDetail from '../components/CatalogCardDetail'
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

function CardThumb({ sport, playerName, imageUrl }) {
  const colors = SPORT_COLORS[sport] || { bg: '#1e1e2e', text: '#888' }
  const initials = playerName
    ? playerName.split(' ').filter(Boolean).map(p => p[0]).slice(0, 2).join('').toUpperCase()
    : '?'
  if (imageUrl) {
    return (
      <div className={styles.cardThumb}>
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

const PER_PAGE = 50

export default function Catalog() {
  const { fmtPrice } = useCurrency()
  const { user } = useAuth()
  const navigate = useNavigate()
  const isLoggedIn = !!user

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

  // Column visibility
  const [visibleCols, setVisibleCols] = useState(loadColPrefs)

  // Collection: owned card IDs + add-to-collection modal
  const [ownedIds,  setOwnedIds]  = useState(new Set())
  const [grades,    setGrades]    = useState([])
  const [addTarget, setAddTarget] = useState(null)
  const [addForm,   setAddForm]   = useState({ grade: 'Raw', quantity: '1', cost_basis: '', purchase_date: '' })
  const [addSaving, setAddSaving] = useState(false)

  // Card detail panel
  const [detailCard,    setDetailCard]    = useState(null)
  const [detailHistory, setDetailHistory] = useState([])
  const [detailLoading, setDetailLoading] = useState(false)

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
      <PageTabs tabs={CATALOG_TABS} />

      <div className={pageStyles.header}>
        <h1 className={pageStyles.title}>Card Catalog</h1>
        <span className={pageStyles.count}>{total.toLocaleString()} cards</span>
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
          <button className={pageStyles.clearBtn} onClick={clearFilters}>Clear</button>
        )}
      </div>

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
        <div className={pageStyles.status}>Loading...</div>
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
                  {visibleCols.variant && (
                    <th className={styles.th}>Variant</th>
                  )}
                  {visibleCols.team && (
                    <th className={styles.th}>Team</th>
                  )}
                  <th
                    className={`${styles.th} ${styles.sortable} ${styles.thRight}`}
                    onClick={() => handleSort('fair_value')}
                  >
                    Price
                    {sortKey === 'fair_value' && <span className={styles.sortArrow}>{sortDir === 'asc' ? ' ↑' : ' ↓'}</span>}
                  </th>
                  {visibleCols.confidence && (
                    <th className={styles.th}>Conf.</th>
                  )}
                  {visibleCols.num_sales && (
                    <th className={`${styles.th} ${styles.thRight}`}>Sales</th>
                  )}
                  <th className={styles.th} style={{ width: 72 }} />
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
                    <td className={`${styles.td} ${styles.tdThumb}`}>
                      <CardThumb
                        sport={row.sport}
                        playerName={row.player_name}
                        imageUrl={row.image_url}
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

                    {/* Optional: Variant (full column when toggled on) */}
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
                      <td className={styles.td}>
                        {row.confidence
                          ? <span className={`${styles.conf} ${styles['conf_' + row.confidence]}`}>{row.confidence}</span>
                          : <span className={styles.muted}>—</span>
                        }
                      </td>
                    )}

                    {/* Optional: Sales */}
                    {visibleCols.num_sales && (
                      <td className={`${styles.td} ${styles.tdRight}`}>
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
              <button className={styles.pgBtn} onClick={() => goTo(1)}       disabled={page === 1}>«</button>
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
              <button className={styles.pgBtn} onClick={() => goTo(pages)}     disabled={page === pages}>»</button>
              <span className={styles.pgInfo}>
                Page {page} of {pages.toLocaleString()} &nbsp;·&nbsp; {total.toLocaleString()} results
              </span>
            </div>
          )}
        </>
      )}

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
