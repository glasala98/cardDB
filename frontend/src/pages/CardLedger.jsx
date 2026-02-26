import { useState, useEffect, useMemo } from 'react'
import { useNavigate } from 'react-router-dom'
import TrendBadge from '../components/TrendBadge'
import ConfidenceBadge from '../components/ConfidenceBadge'
import ConfirmDialog from '../components/ConfirmDialog'
import EditCardModal from '../components/EditCardModal'
import AddCardModal from '../components/AddCardModal'
import ScanCardModal from '../components/ScanCardModal'
import BulkUploadModal from '../components/BulkUploadModal'
import ScrapeProgressModal from '../components/ScrapeProgressModal'
import { getCards, archiveCard, scrapeCard } from '../api/cards'
import { triggerScrape } from '../api/stats'
import { useCurrency } from '../context/CurrencyContext'
import CurrencySelect from '../components/CurrencySelect'
import styles from './CardLedger.module.css'
import pageStyles from './Page.module.css'

const TRENDS = ['up', 'stable', 'down', 'no data']

// Build the subset/card#/serial line without duplication
function buildSubsetLine(card) {
  const parts = []
  if (card.subset) parts.push(card.subset)
  // Only add card# if subset doesn't already contain it
  if (card.card_number && !card.subset?.includes(`#${card.card_number}`)) {
    parts.push(`#${card.card_number}`)
  }
  // Serial: show as "/NNN" (just the print run limit, last number)
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
  const navigate = useNavigate()
  const { fmtPrice } = useCurrency()

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

  const [editTarget,    setEditTarget]    = useState(null)
  const [archiveTarget, setArchiveTarget] = useState(null)
  const [scraping,      setScraping]      = useState({})
  const [showAdd,       setShowAdd]       = useState(false)
  const [showScan,      setShowScan]      = useState(false)
  const [showBulk,      setShowBulk]      = useState(false)
  const [toast,         setToast]         = useState(null)
  const [scrapeAll,          setScrapeAll]          = useState(false)
  const [scrapeEta,          setScrapeEta]          = useState(null)
  const [showScrapeProgress, setShowScrapeProgress] = useState(false)

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

  const years    = useMemo(() => [...new Set(cards.map(c => c.year).filter(Boolean))].sort(), [cards])
  const grades   = useMemo(() => [...new Set(cards.map(c => c.grade).filter(Boolean))].sort(), [cards])
  const sets     = useMemo(() => [...new Set(cards.map(c => c.set_name).filter(Boolean))].sort(), [cards])
  const allTags  = useMemo(() => {
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

  const totalValue  = cards.reduce((s, c) => s + (c.fair_value ?? 0), 0)
  const totalCost   = cards.reduce((s, c) => s + (c.cost_basis ?? 0), 0)
  const totalGain   = totalValue - totalCost
  const priceMin    = Math.floor(Math.min(...cards.map(c => c.fair_value ?? 0).filter(v => v > 0)) || 0)
  const priceMax    = Math.ceil(Math.max(...cards.map(c => c.fair_value ?? 0)) || 0)
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

  const handleArchive = async () => {
    try {
      await archiveCard(archiveTarget)
      setCards(prev => prev.filter(c => c.card_name !== archiveTarget))
      showToast(`Archived successfully`)
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
    try {
      const res = await triggerScrape()
      setScrapeEta({ mins: res.estimated_minutes, cards: res.card_count })
      setShowScrapeProgress(true)
    } catch (e) {
      const msg = e.message?.includes('GITHUB_TOKEN')
        ? 'Rescrape All requires a GITHUB_TOKEN in the server .env — use the ⟳ button on individual cards instead'
        : e.message?.includes('403') || e.message?.includes('admin rights')
        ? 'GitHub token needs both "repo" and "workflow" scopes — regenerate at github.com/settings/tokens'
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

  const SortTh = ({ col, label }) => (
    <th className={styles.th} onClick={() => handleSort(col)}>
      {label}
      {sortKey === col && <span className={styles.arrow}>{sortDir === 'asc' ? ' ↑' : ' ↓'}</span>}
    </th>
  )

  const fmt = v => fmtPrice(v)
  const filtersActive = search || minPrice || maxPrice || yearFilter || gradeFilter || confFilter || setFilter || tagFilter || trendFilter.size < TRENDS.length

  const exportCsv = () => {
    const rows = filtered
    const header = ['Card Name','Fair Value','Cost Basis','Purchase Date','Tags','Trend','Num Sales','Last Scraped','Confidence','Year','Grade']
    const lines = [header.join(',')]
    rows.forEach(c => {
      const row = [
        `"${(c.card_name || '').replace(/"/g, '""')}"`,
        c.fair_value ?? '',
        c.cost_basis ?? '',
        `"${c.purchase_date || ''}"`,
        `"${(c.tags || '').replace(/"/g, '""')}"`,
        c.trend || '',
        c.num_sales || 0,
        c.last_scraped || '',
        c.confidence || '',
        c.year || '',
        c.grade || '',
      ]
      lines.push(row.join(','))
    })
    const blob = new Blob([lines.join('\n')], { type: 'text/csv' })
    const url = URL.createObjectURL(blob)
    const a = document.createElement('a')
    a.href = url; a.download = 'card_ledger.csv'; a.click()
    URL.revokeObjectURL(url)
  }

  return (
    <div className={pageStyles.page}>

      {toast && <div className={`${styles.toast} ${styles[toast.type]}`}>{toast.msg}</div>}

      <div className={pageStyles.header}>
        <h1 className={pageStyles.title}>Card Ledger</h1>
        <span className={pageStyles.count}>{cards.length} cards</span>
        <button
          className={styles.scrapeAllBtn}
          onClick={handleScrapeAll}
          disabled={scrapeAll}
          title="Trigger a full rescrape via GitHub Actions"
        >
          {scrapeAll ? 'Dispatching…' : '⟳ Rescrape All'}
        </button>
        <button
          className={styles.scrapeEta}
          onClick={() => setShowScrapeProgress(true)}
          title="Check GitHub Actions scrape status"
        >
          ⟳ View Status
        </button>
        <button className={styles.exportBtn} onClick={exportCsv} title="Export visible cards to CSV">↓ Export</button>
        <button className={styles.exportBtn} onClick={() => setShowBulk(true)} title="Bulk import from CSV">↑ Bulk Import</button>
        <button className={styles.scanBtn} onClick={() => setShowScan(true)} title="Scan card with AI">📷 Scan Card</button>
        <button className={styles.addBtn} onClick={() => setShowAdd(true)}>+ Add Card</button>
        <CurrencySelect />
      </div>

      {!loading && !error && (
        <div className={styles.stats}>
          <Stat label="Total Value"  value={fmtPrice(totalValue)} />
          <Stat label="Total Cost"   value={fmtPrice(totalCost)} />
          <Stat label="Gain / Loss"  value={`${totalGain >= 0 ? '+' : ''}${fmtPrice(Math.abs(totalGain))}`} gain={totalGain} />
          <Stat label="Avg Value"    value={fmtPrice(cards.length ? totalValue / cards.length : 0)} />
          {mostValuable && (
            <Stat
              label="Most Valuable"
              value={fmtPrice(mostValuable.fair_value)}
              sub={mostValuable.card_name}
            />
          )}
          <Stat label="Showing"      value={`${filtered.length} / ${cards.length}`} />
        </div>
      )}

      <div className={styles.filters}>
        <input
          className={pageStyles.search}
          placeholder="Search cards..."
          value={search}
          onChange={e => setSearch(e.target.value)}
        />

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

        <div className={styles.priceRange}>
          <input
            className={styles.priceInput}
            type="number" min={0}
            placeholder={`Min $${priceMin}`}
            value={minPrice}
            onChange={e => setMinPrice(e.target.value)}
          />
          <span className={styles.priceSep}>–</span>
          <input
            className={styles.priceInput}
            type="number" min={0}
            placeholder={`Max $${priceMax}`}
            value={maxPrice}
            onChange={e => setMaxPrice(e.target.value)}
          />
        </div>

        <select className={styles.filterSelect} value={setFilter} onChange={e => setSetFilter(e.target.value)}>
          <option value="">All Sets</option>
          {sets.map(s => <option key={s} value={s}>{s}</option>)}
        </select>

        <select className={styles.filterSelect} value={gradeFilter} onChange={e => setGradeFilter(e.target.value)}>
          <option value="">All Grades</option>
          {grades.map(g => <option key={g} value={g}>{g}</option>)}
        </select>

        <select className={styles.filterSelect} value={yearFilter} onChange={e => setYearFilter(e.target.value)}>
          <option value="">All Years</option>
          {years.map(y => <option key={y} value={y}>{y}</option>)}
        </select>

        <select className={styles.filterSelect} value={tagFilter} onChange={e => setTagFilter(e.target.value)}>
          <option value="">All Tags</option>
          {allTags.map(t => <option key={t} value={t}>{t}</option>)}
        </select>

        <select className={styles.filterSelect} value={confFilter} onChange={e => setConfFilter(e.target.value)}>
          <option value="">All Confidence</option>
          <option value="high">High</option>
          <option value="medium">Medium</option>
          <option value="low">Low</option>
          <option value="estimated">Estimated</option>
          <option value="not found">Not Found</option>
        </select>

        {filtersActive && (
          <button className={styles.clearBtn} onClick={() => {
            setSearch(''); setMinPrice(''); setMaxPrice('')
            setYearFilter(''); setGradeFilter(''); setConfFilter('')
            setSetFilter(''); setTagFilter('')
            setTrendFilter(new Set(TRENDS))
          }}>
            Clear filters
          </button>
        )}
      </div>

      {loading && <p className={pageStyles.status}>Loading…</p>}
      {error   && <p className={pageStyles.error}>Error: {error}</p>}

      {!loading && !error && (
        <div className={styles.tableWrap}>
          <table className={styles.table}>
            <thead>
              <tr>
                <SortTh col="player"       label="Card" />
                <SortTh col="fair_value"   label="Fair Value" />
                <SortTh col="cost_basis"   label="Cost Basis" />
                <SortTh col="trend"        label="Trend" />
                <th className={styles.th}>Confidence</th>
                <SortTh col="last_scraped" label="Last Scraped" />
                <SortTh col="num_sales"    label="Sales" />
                <th className={styles.th}>Tags</th>
                <th className={styles.th}>Actions</th>
              </tr>
            </thead>
            <tbody>
              {filtered.length === 0 && (
                <tr><td colSpan={9} className={styles.empty}>No cards match the current filters.</td></tr>
              )}
              {filtered.map(card => (
                <tr key={card.card_name} className={styles.tr}>
                  <td
                    className={`${styles.td} ${styles.nameCell}`}
                    onClick={() => navigate(`/ledger/${encodeURIComponent(card.card_name)}`)}
                    title={card.card_name}
                  >
                    <span className={styles.cardPlayer}>
                      {card.player || card.card_name}
                    </span>
                    {buildSubsetLine(card) && (
                      <span className={styles.cardSubset}>
                        {buildSubsetLine(card)}
                      </span>
                    )}
                    <span className={styles.cardMeta}>
                      {[card.year, card.set_name, card.grade].filter(Boolean).join(' · ')}
                    </span>
                  </td>
                  <td className={styles.td}>{fmt(card.fair_value)}</td>
                  <td className={styles.td}>{fmt(card.cost_basis)}</td>
                  <td className={styles.td}><TrendBadge trend={card.trend} /></td>
                  <td className={styles.td}><ConfidenceBadge confidence={card.confidence} /></td>
                  <td className={styles.td}>
                    <ScrapedCell dateStr={card.last_scraped} />
                  </td>
                  <td className={styles.td}>{card.num_sales || '—'}</td>
                  <td className={styles.td}><span className={styles.tags}>{card.tags || '—'}</span></td>
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
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      {showScrapeProgress && (
        <ScrapeProgressModal
          estimatedMins={scrapeEta?.mins}
          onClose={() => { setShowScrapeProgress(false); load() }}
        />
      )}
      {showAdd      && <AddCardModal     onClose={() => setShowAdd(false)}  onAdded={handleAdded} />}
      {showScan     && <ScanCardModal    onClose={() => setShowScan(false)} onAdded={() => { setShowScan(false); load() }} />}
      {showBulk     && <BulkUploadModal  onClose={() => setShowBulk(false)} onImported={() => { setShowBulk(false); load() }} />}
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

function ScrapedCell({ dateStr }) {
  if (!dateStr) return <span className={styles.scrapedNone}>—</span>
  const days = daysSince(dateStr)
  const cls = days == null ? '' : days > 30 ? styles.scrapedOld : days > 7 ? styles.scrapedWarn : styles.scrapedOk
  return <span className={`${styles.scrapedDate} ${cls}`} title={`${days ?? '?'} days ago`}>{dateStr}</span>
}

function Stat({ label, value, gain, sub }) {
  const cls = gain == null ? '' : gain >= 0 ? styles.gain : styles.loss
  return (
    <div className={styles.stat}>
      <span className={styles.statLabel}>{label}</span>
      <span className={`${styles.statValue} ${cls}`}>{value}</span>
      {sub && <span className={styles.statSub} title={sub}>{sub}</span>}
    </div>
  )
}
