import { useState, useEffect, useMemo } from 'react'
import { useNavigate } from 'react-router-dom'
import TrendBadge from '../components/TrendBadge'
import ConfirmDialog from '../components/ConfirmDialog'
import EditCardModal from '../components/EditCardModal'
import AddCardModal from '../components/AddCardModal'
import { getCards, archiveCard, scrapeCard } from '../api/cards'
import { triggerScrape } from '../api/stats'
import { useCurrency } from '../context/CurrencyContext'
import styles from './CardLedger.module.css'
import pageStyles from './Page.module.css'

const TRENDS = ['up', 'stable', 'down', 'no data']

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

  const [sortKey, setSortKey] = useState('card_name')
  const [sortDir, setSortDir] = useState('asc')

  const [editTarget,    setEditTarget]    = useState(null)
  const [archiveTarget, setArchiveTarget] = useState(null)
  const [scraping,      setScraping]      = useState({})
  const [showAdd,       setShowAdd]       = useState(false)
  const [toast,         setToast]         = useState(null)
  const [scrapeAll,     setScrapeAll]     = useState(false)   // loading state
  const [scrapeEta,     setScrapeEta]     = useState(null)    // { mins, cards } after dispatch

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

  const filtered = useMemo(() => {
    const s = search.toLowerCase()
    return cards
      .filter(c => {
        if (s && !c.card_name?.toLowerCase().includes(s)) return false
        const trend = (c.trend || 'no data').toLowerCase()
        if (!trendFilter.has(trend)) return false
        if (minPrice !== '' && (c.fair_value ?? 0) < Number(minPrice)) return false
        if (maxPrice !== '' && (c.fair_value ?? 0) > Number(maxPrice)) return false
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
  }, [cards, search, trendFilter, minPrice, maxPrice, sortKey, sortDir])

  const totalValue = cards.reduce((s, c) => s + (c.fair_value ?? 0), 0)
  const totalCost  = cards.reduce((s, c) => s + (c.cost_basis ?? 0), 0)
  const totalGain  = totalValue - totalCost
  const priceMin   = Math.floor(Math.min(...cards.map(c => c.fair_value ?? 0).filter(v => v > 0)) || 0)
  const priceMax   = Math.ceil(Math.max(...cards.map(c => c.fair_value ?? 0)) || 0)

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
      showToast(`Scrape dispatched — ~${res.estimated_minutes} min for ${res.card_count} cards`)
    } catch (e) {
      showToast(e.message, 'error')
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
  const filtersActive = search || minPrice || maxPrice || trendFilter.size < TRENDS.length

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
        {scrapeEta && (
          <span className={styles.scrapeEta}>
            ~{scrapeEta.mins} min ({scrapeEta.cards} cards)
          </span>
        )}
        <button className={styles.addBtn} onClick={() => setShowAdd(true)}>+ Add Card</button>
      </div>

      {!loading && !error && (
        <div className={styles.stats}>
          <Stat label="Total Value"  value={fmtPrice(totalValue)} />
          <Stat label="Total Cost"   value={fmtPrice(totalCost)} />
          <Stat label="Gain / Loss"  value={`${totalGain >= 0 ? '+' : ''}${fmtPrice(Math.abs(totalGain))}`} gain={totalGain} />
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

        {filtersActive && (
          <button className={styles.clearBtn} onClick={() => {
            setSearch(''); setMinPrice(''); setMaxPrice(''); setTrendFilter(new Set(TRENDS))
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
                <SortTh col="card_name"  label="Card Name" />
                <SortTh col="fair_value" label="Fair Value" />
                <SortTh col="cost_basis" label="Cost Basis" />
                <SortTh col="trend"      label="Trend" />
                <SortTh col="num_sales"  label="Sales" />
                <th className={styles.th}>Tags</th>
                <th className={styles.th}>Actions</th>
              </tr>
            </thead>
            <tbody>
              {filtered.length === 0 && (
                <tr><td colSpan={7} className={styles.empty}>No cards match the current filters.</td></tr>
              )}
              {filtered.map(card => (
                <tr key={card.card_name} className={styles.tr}>
                  <td
                    className={`${styles.td} ${styles.nameCell}`}
                    onClick={() => navigate(`/ledger/${encodeURIComponent(card.card_name)}`)}
                    title={card.card_name}
                  >
                    {card.card_name}
                  </td>
                  <td className={styles.td}>{fmt(card.fair_value)}</td>
                  <td className={styles.td}>{fmt(card.cost_basis)}</td>
                  <td className={styles.td}><TrendBadge trend={card.trend} /></td>
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

      {showAdd      && <AddCardModal  onClose={() => setShowAdd(false)}    onAdded={handleAdded} />}
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

function Stat({ label, value, gain }) {
  const cls = gain == null ? '' : gain >= 0 ? styles.gain : styles.loss
  return (
    <div className={styles.stat}>
      <span className={styles.statLabel}>{label}</span>
      <span className={`${styles.statValue} ${cls}`}>{value}</span>
    </div>
  )
}
