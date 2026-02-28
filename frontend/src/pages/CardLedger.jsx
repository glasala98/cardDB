import { useState, useEffect, useMemo, useRef } from 'react'
import { useNavigate } from 'react-router-dom'
import TrendBadge from '../components/TrendBadge'
import ConfidenceBadge from '../components/ConfidenceBadge'
import ConfirmDialog from '../components/ConfirmDialog'
import EditCardModal from '../components/EditCardModal'
import AddCardModal from '../components/AddCardModal'
import ScanCardModal from '../components/ScanCardModal'
import BulkUploadModal from '../components/BulkUploadModal'
import ScrapeProgressModal from '../components/ScrapeProgressModal'
import { getCards, archiveCard, scrapeCard, updateCard } from '../api/cards'
import { triggerScrape } from '../api/stats'
import { useCurrency } from '../context/CurrencyContext'
import { usePublicMode } from '../context/PublicModeContext'
import CurrencySelect from '../components/CurrencySelect'
import styles from './CardLedger.module.css'
import pageStyles from './Page.module.css'

const TRENDS = ['up', 'stable', 'down', 'no data']

function buildSubsetLine(card) {
  const parts = []
  if (card.subset) parts.push(card.subset)
  if (card.card_number && !card.subset?.includes(`#${card.card_number}`)) {
    parts.push(`#${card.card_number}`)
  }
  if (card.serial) {
    const run = card.serial.includes('/') ? card.serial.split('/').pop() : card.serial
    parts.push(`/${run}`)
  }
  return parts.join(' ')
}

function daysSince(dateStr) {
  if (!dateStr) return null
  const d = new Date(dateStr)
  if (isNaN(d)) return null
  return Math.floor((Date.now() - d.getTime()) / 86400000)
}

export default function CardLedger() {
  const navigate   = useNavigate()
  const { fmtPrice } = useCurrency()
  const isPublic   = usePublicMode()

  const [cards,   setCards]   = useState([])
  const [loading, setLoading] = useState(true)
  const [error,   setError]   = useState(null)

  const [search,      setSearch]      = useState('')
  const [trendFilter, setTrendFilter] = useState(new Set(TRENDS))
  const [minPrice,    setMinPrice]    = useState('')
  const [maxPrice,    setMaxPrice]    = useState('')
  const [yearFilter,  setYearFilter]  = useState('')
  const [gradeFilter, setGradeFilter] = useState('')
  const [confFilter,  setConfFilter]  = useState('')
  const [setFilter,   setSetFilter]   = useState('')
  const [tagFilter,   setTagFilter]   = useState('')

  const [sortKey, setSortKey] = useState('card_name')
  const [sortDir, setSortDir] = useState('asc')

  const [costEdit,      setCostEdit]      = useState(null)
  const [editTarget,    setEditTarget]    = useState(null)
  const [archiveTarget, setArchiveTarget] = useState(null)
  const [scraping,      setScraping]      = useState({})
  const [showAdd,       setShowAdd]       = useState(false)
  const [showScan,      setShowScan]      = useState(false)
  const [showBulk,      setShowBulk]      = useState(false)
  const [showTools,     setShowTools]     = useState(false)
  const [toast,         setToast]         = useState(null)
  const [scrapeAll,          setScrapeAll]          = useState(false)
  const [scrapeEta,          setScrapeEta]          = useState(null)
  const [showScrapeProgress, setShowScrapeProgress] = useState(false)

  const toolsRef = useRef(null)

  useEffect(() => {
    const handler = e => {
      if (toolsRef.current && !toolsRef.current.contains(e.target)) setShowTools(false)
    }
    document.addEventListener('mousedown', handler)
    return () => document.removeEventListener('mousedown', handler)
  }, [])

  const load = () => {
    setLoading(true)
    getCards()
      .then(data => { setCards(data.cards || []); setError(null) })
      .catch(e => setError(e.message))
      .finally(() => setLoading(false))
  }
  useEffect(load, [])

  const showToast = (msg, type = 'success') => {
    setToast({ msg, type })
    setTimeout(() => setToast(null), 3500)
  }

  const years   = useMemo(() => [...new Set(cards.map(c => c.year).filter(Boolean))].sort(), [cards])
  const grades  = useMemo(() => [...new Set(cards.map(c => c.grade).filter(Boolean))].sort(), [cards])
  const sets    = useMemo(() => [...new Set(cards.map(c => c.set_name).filter(Boolean))].sort(), [cards])
  const allTags = useMemo(() => {
    const t = new Set()
    cards.forEach(c => (c.tags || '').split(',').forEach(tag => { const s = tag.trim(); if (s) t.add(s) }))
    return [...t].sort()
  }, [cards])

  const filtered = useMemo(() => {
    const s = search.toLowerCase()
    return cards
      .filter(c => {
        if (s && !(
          c.card_name?.toLowerCase().includes(s) ||
          c.player?.toLowerCase().includes(s) ||
          c.set_name?.toLowerCase().includes(s) ||
          c.year?.toString().includes(s) ||
          c.grade?.toLowerCase().includes(s)
        )) return false
        const trend = (c.trend || 'no data').toLowerCase()
        if (!trendFilter.has(trend)) return false
        if (minPrice !== '' && (c.fair_value ?? 0) < Number(minPrice)) return false
        if (maxPrice !== '' && (c.fair_value ?? 0) > Number(maxPrice)) return false
        if (yearFilter  && c.year     !== yearFilter)  return false
        if (gradeFilter && c.grade    !== gradeFilter) return false
        if (setFilter   && c.set_name !== setFilter)   return false
        if (tagFilter   && !(c.tags || '').split(',').map(t => t.trim()).includes(tagFilter)) return false
        if (confFilter) {
          const conf = (c.confidence || '').toLowerCase()
          if (confFilter === 'not found' ? conf !== 'not found' : !conf.startsWith(confFilter)) return false
        }
        return true
      })
      .sort((a, b) => {
        const av = a[sortKey] ?? ''
        const bv = b[sortKey] ?? ''
        const cmp = typeof av === 'number' && typeof bv === 'number'
          ? av - bv
          : String(av).localeCompare(String(bv), undefined, { numeric: true })
        return sortDir === 'asc' ? cmp : -cmp
      })
  }, [cards, search, trendFilter, minPrice, maxPrice, yearFilter, gradeFilter, confFilter, setFilter, tagFilter, sortKey, sortDir])

  const totalValue   = cards.reduce((s, c) => s + (c.fair_value  ?? 0), 0)
  const totalCost    = cards.reduce((s, c) => s + (c.cost_basis  ?? 0), 0)
  const totalGain    = totalValue - totalCost
  const priceMin     = Math.floor(Math.min(...cards.map(c => c.fair_value ?? 0).filter(v => v > 0)) || 0)
  const priceMax     = Math.ceil(Math.max(...cards.map(c => c.fair_value  ?? 0)) || 0)
  const mostValuable = cards.length ? cards.reduce((best, c) => (c.fair_value ?? 0) > (best.fair_value ?? 0) ? c : best, cards[0]) : null

  const handleSort = key => {
    if (sortKey === key) setSortDir(d => d === 'asc' ? 'desc' : 'asc')
    else { setSortKey(key); setSortDir('asc') }
  }

  const toggleTrend = trend => {
    setTrendFilter(prev => {
      const next = new Set(prev)
      next.has(trend) ? next.delete(trend) : next.add(trend)
      return next
    })
  }

  const clearFilters = () => {
    setSearch(''); setMinPrice(''); setMaxPrice('')
    setYearFilter(''); setGradeFilter(''); setConfFilter('')
    setSetFilter(''); setTagFilter('')
    setTrendFilter(new Set(TRENDS))
  }

  const handleArchive = async () => {
    try {
      await archiveCard(archiveTarget)
      setCards(prev => prev.filter(c => c.card_name !== archiveTarget))
      showToast('Archived successfully')
    } catch (e) {
      showToast(e.message, 'error')
    } finally {
      setArchiveTarget(null)
    }
  }

  const handleAdded = () => { setShowAdd(false); load() }

  const handleScrapeAll = async () => {
    setScrapeAll(true)
    setScrapeEta(null)
    setShowTools(false)
    try {
      const res = await triggerScrape()
      setScrapeEta({ mins: res.estimated_minutes, cards: res.card_count })
      setShowScrapeProgress(true)
    } catch (e) {
      const msg = e.message?.includes('GITHUB_TOKEN')
        ? 'Rescrape All requires a GITHUB_TOKEN in the server .env'
        : e.message?.includes('403') || e.message?.includes('admin rights')
        ? 'GitHub token needs "repo" and "workflow" scopes'
        : e.message
      showToast(msg, 'error')
    } finally {
      setScrapeAll(false)
    }
  }

  const handleScrape = async cardName => {
    setScraping(prev => ({ ...prev, [cardName]: true }))
    try {
      await scrapeCard(cardName)
      showToast('Scrape queued — refresh in ~30s to see updated price')
    } catch (e) {
      showToast(e.message, 'error')
    } finally {
      setScraping(prev => ({ ...prev, [cardName]: false }))
    }
  }

  const handleCostSave = async (cardName, rawVal) => {
    const num = parseFloat(rawVal)
    setCostEdit(null)
    if (isNaN(num) || num < 0) return
    try {
      await updateCard(cardName, { cost_basis: num })
      setCards(prev => prev.map(c => c.card_name === cardName ? { ...c, cost_basis: num } : c))
      showToast(`Cost basis updated to ${fmtPrice(num)}`)
    } catch (e) {
      showToast(e.message, 'error')
    }
  }

  const exportCsv = () => {
    const header = ['Card Name','Fair Value','Cost Basis','Purchase Date','Tags','Trend','Num Sales','Last Scraped','Confidence','Year','Grade']
    const lines  = [header.join(',')]
    filtered.forEach(c => {
      lines.push([
        `"${(c.card_name || '').replace(/"/g, '""')}"`,
        c.fair_value ?? '', c.cost_basis ?? '',
        `"${c.purchase_date || ''}"`, `"${(c.tags || '').replace(/"/g, '""')}"`,
        c.trend || '', c.num_sales || 0, c.last_scraped || '',
        c.confidence || '', c.year || '', c.grade || '',
      ].join(','))
    })
    const a = document.createElement('a')
    a.href = URL.createObjectURL(new Blob([lines.join('\n')], { type: 'text/csv' }))
    a.download = 'card_ledger.csv'; a.click()
  }

  const SortTh = ({ col, label }) => (
    <th className={styles.th} onClick={() => handleSort(col)}>
      {label}
      {sortKey === col && <span className={styles.arrow}>{sortDir === 'asc' ? ' ↑' : ' ↓'}</span>}
    </th>
  )

  const fmt = v => fmtPrice(v)
  const filtersActive = search || minPrice || maxPrice || yearFilter || gradeFilter || confFilter || setFilter || tagFilter || trendFilter.size < TRENDS.length

  return (
    <div className={pageStyles.page}>

      {toast && <div className={`${styles.toast} ${styles[toast.type]}`}>{toast.msg}</div>}

      {/* ── Top bar ───────────────────────────────────────────── */}
      <div className={styles.topBar}>
        <div className={styles.topBarLeft}>
          <h1 className={styles.pageTitle}>Card Ledger</h1>
          <span className={styles.countBadge}>{cards.length} cards</span>
          {filtered.length !== cards.length && (
            <span className={styles.filteredBadge}>{filtered.length} shown</span>
          )}
        </div>
        <div className={styles.topBarRight}>
          <CurrencySelect />
          {isPublic && (
            <button className={styles.toolsBtn} onClick={exportCsv}>↓ Export</button>
          )}
          {!isPublic && (
            <div className={styles.toolsWrap} ref={toolsRef}>
              <button className={styles.toolsBtn} onClick={() => setShowTools(v => !v)}>
                Tools {showTools ? '▴' : '▾'}
              </button>
              {showTools && (
                <div className={styles.toolsDropdown}>
                  <button className={styles.toolsItem} onClick={handleScrapeAll} disabled={scrapeAll}>
                    {scrapeAll ? 'Dispatching…' : '⟳ Rescrape All'}
                  </button>
                  <button className={styles.toolsItem} onClick={() => { setShowScrapeProgress(true); setShowTools(false) }}>
                    ⟳ View Status
                  </button>
                  <div className={styles.toolsDivider} />
                  <button className={styles.toolsItem} onClick={() => { exportCsv(); setShowTools(false) }}>
                    ↓ Export CSV
                  </button>
                  <button className={styles.toolsItem} onClick={() => { setShowBulk(true); setShowTools(false) }}>
                    ↑ Bulk Import
                  </button>
                  <button className={styles.toolsItem} onClick={() => { setShowScan(true); setShowTools(false) }}>
                    📷 Scan Card
                  </button>
                </div>
              )}
            </div>
          )}
          {!isPublic && (
            <button className={styles.addBtn} onClick={() => setShowAdd(true)}>+ Add Card</button>
          )}
        </div>
      </div>

      {/* ── Compact stats strip ───────────────────────────────── */}
      {!loading && !error && (
        <div className={styles.statsStrip}>
          <StatChip label="Total Value"  value={fmtPrice(totalValue)} />
          <StatChip label="Total Cost"   value={fmtPrice(totalCost)} />
          <StatChip label="Gain / Loss"  value={`${totalGain >= 0 ? '+' : ''}${fmtPrice(Math.abs(totalGain))}`} gain={totalGain} />
          <StatChip label="Avg Value"    value={fmtPrice(cards.length ? totalValue / cards.length : 0)} />
          {mostValuable && (
            <StatChip label="Top Card" value={fmtPrice(mostValuable.fair_value)} sub={mostValuable.player || mostValuable.card_name} />
          )}
        </div>
      )}

      {/* ── Layout: sidebar + table ───────────────────────────── */}
      <div className={styles.layout}>

        {/* Filter sidebar */}
        <aside className={styles.filterPanel}>

          <div className={styles.filterSection}>
            <input
              className={styles.sideSearch}
              placeholder="Search cards…"
              value={search}
              onChange={e => setSearch(e.target.value)}
            />
          </div>

          <div className={styles.filterSection}>
            <span className={styles.filterLabel}>Trend</span>
            <div className={styles.trendBtns}>
              {TRENDS.map(t => (
                <button
                  key={t}
                  className={`${styles.trendBtn} ${trendFilter.has(t) ? styles.on : styles.off}`}
                  onClick={() => toggleTrend(t)}
                >
                  <TrendBadge trend={t} />
                </button>
              ))}
            </div>
          </div>

          <div className={styles.filterSection}>
            <span className={styles.filterLabel}>Price</span>
            <div className={styles.priceRow}>
              <input
                className={styles.priceInput}
                type="number" min={0}
                placeholder={`$${priceMin}`}
                value={minPrice}
                onChange={e => setMinPrice(e.target.value)}
              />
              <span className={styles.priceSep}>–</span>
              <input
                className={styles.priceInput}
                type="number" min={0}
                placeholder={`$${priceMax}`}
                value={maxPrice}
                onChange={e => setMaxPrice(e.target.value)}
              />
            </div>
          </div>

          <div className={styles.filterSection}>
            <span className={styles.filterLabel}>Set</span>
            <select className={styles.sideSelect} value={setFilter} onChange={e => setSetFilter(e.target.value)}>
              <option value="">All sets</option>
              {sets.map(s => <option key={s} value={s}>{s}</option>)}
            </select>
          </div>

          <div className={styles.filterSection}>
            <span className={styles.filterLabel}>Grade</span>
            <select className={styles.sideSelect} value={gradeFilter} onChange={e => setGradeFilter(e.target.value)}>
              <option value="">All grades</option>
              {grades.map(g => <option key={g} value={g}>{g}</option>)}
            </select>
          </div>

          <div className={styles.filterSection}>
            <span className={styles.filterLabel}>Year</span>
            <select className={styles.sideSelect} value={yearFilter} onChange={e => setYearFilter(e.target.value)}>
              <option value="">All years</option>
              {years.map(y => <option key={y} value={y}>{y}</option>)}
            </select>
          </div>

          <div className={styles.filterSection}>
            <span className={styles.filterLabel}>Tags</span>
            <select className={styles.sideSelect} value={tagFilter} onChange={e => setTagFilter(e.target.value)}>
              <option value="">All tags</option>
              {allTags.map(t => <option key={t} value={t}>{t}</option>)}
            </select>
          </div>

          <div className={styles.filterSection}>
            <span className={styles.filterLabel}>Confidence</span>
            <select className={styles.sideSelect} value={confFilter} onChange={e => setConfFilter(e.target.value)}>
              <option value="">All</option>
              <option value="high">High</option>
              <option value="medium">Medium</option>
              <option value="low">Low</option>
              <option value="estimated">Estimated</option>
              <option value="not found">Not Found</option>
            </select>
          </div>

          {filtersActive && (
            <button className={styles.clearBtn} onClick={clearFilters}>
              Clear filters
            </button>
          )}
        </aside>

        {/* Main content */}
        <div className={styles.mainArea}>
          {loading && <p className={pageStyles.status}>Loading…</p>}
          {error   && <p className={pageStyles.error}>Error: {error}</p>}

          {!loading && !error && (
            <div className={styles.tableWrap}>
              <table className={styles.table}>
                <thead>
                  <tr>
                    <SortTh col="player"       label="Card" />
                    <SortTh col="fair_value"   label="Fair Value" />
                    <SortTh col="trend"        label="Trend" />
                    <th className={`${styles.th} ${styles.hideTablet}`}>Confidence</th>
                    <SortTh col="num_sales"    label="Sales"       className={styles.hideTablet} />
                    <SortTh col="cost_basis"   label="Cost Basis"  className={styles.hideMobile} />
                    <SortTh col="last_scraped" label="Last Scraped" className={styles.hideTablet} />
                    <th className={`${styles.th} ${styles.hideTablet}`}>Tags</th>
                    {!isPublic && <th className={styles.th}>Actions</th>}
                  </tr>
                </thead>
                <tbody>
                  {filtered.length === 0 && (
                    <tr><td colSpan={isPublic ? 8 : 9} className={styles.empty}>No cards match the current filters.</td></tr>
                  )}
                  {filtered.map(card => (
                    <tr key={card.card_name} className={styles.tr}>
                      <td
                        className={`${styles.td} ${styles.nameCell}`}
                        onClick={() => navigate(`/ledger/${encodeURIComponent(card.card_name)}`)}
                        title={card.card_name}
                      >
                        <span className={styles.cardPlayer}>{card.player || card.card_name}</span>
                        {buildSubsetLine(card) && (
                          <span className={styles.cardSubset}>{buildSubsetLine(card)}</span>
                        )}
                        <span className={styles.cardMeta}>
                          {[
                            card.year,
                            card.set_name?.startsWith(card.year)
                              ? card.set_name.slice(card.year.length).trim()
                              : card.set_name,
                            card.grade,
                          ].filter(Boolean).join(' · ')}
                        </span>
                      </td>
                      <td className={styles.td}>{fmt(card.fair_value)}</td>
                      <td className={`${styles.td} ${styles.compactCell}`}><TrendBadge trend={card.trend} /></td>
                      <td className={`${styles.td} ${styles.compactCell} ${styles.hideTablet}`}><ConfidenceBadge confidence={card.confidence} /></td>
                      <td className={`${styles.td} ${styles.compactCell} ${styles.hideTablet}`}>{card.num_sales || '—'}</td>
                      <td
                        className={`${styles.td} ${styles.hideMobile} ${!isPublic ? styles.editableCell : ''}`}
                        onClick={() => !isPublic && costEdit !== card.card_name && setCostEdit(card.card_name)}
                        title={isPublic ? undefined : 'Click to edit cost basis'}
                      >
                        {!isPublic && costEdit === card.card_name ? (
                          <InlineCostInput
                            initial={card.cost_basis}
                            onSave={val => handleCostSave(card.card_name, val)}
                            onCancel={() => setCostEdit(null)}
                          />
                        ) : (
                          <span className={styles.editableValue}>{fmt(card.cost_basis)}</span>
                        )}
                      </td>
                      <td className={`${styles.td} ${styles.compactCell} ${styles.hideTablet}`}><ScrapedCell dateStr={card.last_scraped} /></td>
                      <td className={`${styles.td} ${styles.compactCell} ${styles.hideTablet}`}><span className={styles.tags}>{card.tags || '—'}</span></td>
                      {!isPublic && (
                        <td className={styles.td}>
                          <div className={styles.actions}>
                            <button className={styles.btnEdit}    onClick={() => setEditTarget(card)}>Edit</button>
                            <button
                              className={styles.btnScrape}
                              onClick={() => handleScrape(card.card_name)}
                              disabled={scraping[card.card_name]}
                              title="Re-scrape eBay price"
                            >
                              {scraping[card.card_name] ? '…' : '⟳'}
                            </button>
                            <button className={styles.btnArchive} onClick={() => setArchiveTarget(card.card_name)}>Archive</button>
                          </div>
                        </td>
                      )}
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </div>
      </div>

      {/* ── Modals ────────────────────────────────────────────── */}
      {showScrapeProgress && (
        <ScrapeProgressModal
          estimatedMins={scrapeEta?.mins}
          onClose={() => { setShowScrapeProgress(false); load() }}
        />
      )}
      {showAdd      && <AddCardModal    onClose={() => setShowAdd(false)}  onAdded={handleAdded} />}
      {showScan     && <ScanCardModal   onClose={() => setShowScan(false)} onAdded={() => { setShowScan(false); load() }} />}
      {showBulk     && <BulkUploadModal onClose={() => setShowBulk(false)} onImported={() => { setShowBulk(false); load() }} />}
      {editTarget   && <EditCardModal card={editTarget} onClose={() => setEditTarget(null)} onSaved={() => { setEditTarget(null); load() }} />}
      {archiveTarget && (
        <ConfirmDialog
          message={`Archive "${archiveTarget.length > 80 ? archiveTarget.slice(0, 80) + '…' : archiveTarget}"? It can be restored from the archive later.`}
          confirmLabel="Archive"
          danger
          onConfirm={handleArchive}
          onCancel={() => setArchiveTarget(null)}
        />
      )}
    </div>
  )
}

function InlineCostInput({ initial, onSave, onCancel }) {
  const [val, setVal] = useState(String(initial ?? ''))
  const cancelRef = useRef(false)
  return (
    <input
      type="number" step="0.01" min="0" autoFocus
      value={val}
      onChange={e => setVal(e.target.value)}
      onKeyDown={e => {
        if (e.key === 'Enter')  e.currentTarget.blur()
        if (e.key === 'Escape') { cancelRef.current = true; e.currentTarget.blur() }
      }}
      onBlur={() => {
        if (cancelRef.current) { cancelRef.current = false; onCancel(); return }
        onSave(val)
      }}
      onClick={e => e.stopPropagation()}
      className={styles.costInlineInput}
    />
  )
}

function ScrapedCell({ dateStr }) {
  if (!dateStr) return <span className={styles.scrapedNone}>—</span>
  const days = daysSince(dateStr)
  const cls  = days == null ? '' : days > 30 ? styles.scrapedOld : days > 7 ? styles.scrapedWarn : styles.scrapedOk
  return <span className={`${styles.scrapedDate} ${cls}`} title={`${days ?? '?'} days ago`}>{dateStr}</span>
}

function StatChip({ label, value, gain, sub }) {
  const cls = gain == null ? '' : gain >= 0 ? styles.gain : styles.loss
  return (
    <div className={styles.statChip}>
      <span className={styles.statLabel}>{label}</span>
      <span className={`${styles.statValue} ${cls}`}>{value}</span>
      {sub && <span className={styles.statSub} title={sub}>{sub}</span>}
    </div>
  )
}
