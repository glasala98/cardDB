import { useState, useEffect, useRef } from 'react'
import { useNavigate, useSearchParams } from 'react-router-dom'
import { getCatalog } from '../api/catalog'
import SourceBadge from '../components/SourceBadge'
import styles from './Search.module.css'

const PAGE_SIZE = 30
const DEBOUNCE_MS = 350

const SPORTS = ['NHL','NBA','NFL','MLB']

function fmt(val) {
  if (val == null) return null
  return '$' + Number(val).toLocaleString('en-US', { minimumFractionDigits: 0, maximumFractionDigits: 0 })
}

export default function Search() {
  const [searchParams, setSearchParams] = useSearchParams()
  const navigate = useNavigate()

  const [player,   setPlayer]   = useState(searchParams.get('player') ?? '')
  const [year,     setYear]     = useState(searchParams.get('year')   ?? '')
  const [setName,  setSetName]  = useState(searchParams.get('set')    ?? '')
  const [variant,  setVariant]  = useState(searchParams.get('variant') ?? '')
  const [sport,    setSport]    = useState(searchParams.get('sport')  ?? '')
  const [isRookie, setIsRookie] = useState(searchParams.get('rookie') === '1')
  const [page,     setPage]     = useState(Number(searchParams.get('page') ?? 1))

  const [results, setResults] = useState(null)  // null = idle, [] = empty
  const [total,   setTotal]   = useState(null)
  const [loading, setLoading] = useState(false)
  const [error,   setError]   = useState(null)

  const debounceRef = useRef(null)
  const reqIdRef    = useRef(0)

  const hasQuery = player.trim().length >= 2 || year || setName.trim().length >= 2 || variant.trim().length >= 2

  useEffect(() => {
    clearTimeout(debounceRef.current)

    if (!hasQuery) {
      setResults(null); setTotal(null); setError(null); setLoading(false)
      return
    }

    debounceRef.current = setTimeout(() => {
      runSearch(player, year, setName, variant, sport, isRookie, page)
    }, DEBOUNCE_MS)

    return () => clearTimeout(debounceRef.current)
  }, [player, year, setName, variant, sport, isRookie, page])  // eslint-disable-line

  async function runSearch(p, y, s, v, sp, rookie, pg) {
    const myId = ++reqIdRef.current
    setLoading(true); setError(null)

    const params = {
      page,
      per_page: PAGE_SIZE,
      sort: 'num_sales',
      dir: 'desc',
    }
    if (p.trim())   params.search   = p.trim()
    if (y)          params.year     = y
    if (s.trim())   params.set_name = s.trim()
    if (sp)         params.sport    = sp
    if (rookie)     params.is_rookie = true

    // sync URL
    const sp2 = new URLSearchParams()
    if (p.trim())   sp2.set('player',  p.trim())
    if (y)          sp2.set('year',    y)
    if (s.trim())   sp2.set('set',     s.trim())
    if (v.trim())   sp2.set('variant', v.trim())
    if (sp)         sp2.set('sport',   sp)
    if (rookie)     sp2.set('rookie',  '1')
    if (pg > 1)     sp2.set('page',    String(pg))
    setSearchParams(sp2, { replace: true })

    try {
      const data = await getCatalog(params)
      if (myId !== reqIdRef.current) return

      // client-side variant filter (catalog API doesn't support variant param yet)
      let cards = data.cards ?? []
      if (v.trim()) {
        const vl = v.trim().toLowerCase()
        cards = cards.filter(c => c.variant?.toLowerCase().includes(vl))
      }

      setResults(cards)
      setTotal(data.total ?? 0)
    } catch (e) {
      if (myId !== reqIdRef.current) return
      setError(e?.message || 'Search failed — please try again.')
      setResults([])
    } finally {
      if (myId === reqIdRef.current) setLoading(false)
    }
  }

  function handleFieldChange(setter) {
    return (e) => { setter(e.target.value); setPage(1) }
  }

  const totalPages = total != null ? Math.ceil(total / PAGE_SIZE) : 0
  const hasSearched = results !== null

  return (
    <div className={styles.page}>
      <div className={styles.hero}>
        <h1 className={styles.heading}>Card Sales Search</h1>
        <p className={styles.sub}>Find a card to see its full sale history.</p>

        <div className={styles.searchGrid}>
          <div className={styles.fieldWrap}>
            <label className={styles.fieldLabel}>Player</label>
            <input
              className={styles.fieldInput}
              placeholder="e.g. Connor McDavid"
              value={player}
              onChange={handleFieldChange(setPlayer)}
              autoFocus
            />
          </div>

          <div className={styles.fieldWrap}>
            <label className={styles.fieldLabel}>Year</label>
            <input
              className={styles.fieldInput}
              placeholder="e.g. 2015-16"
              value={year}
              onChange={handleFieldChange(setYear)}
            />
          </div>

          <div className={styles.fieldWrap}>
            <label className={styles.fieldLabel}>Set</label>
            <input
              className={styles.fieldInput}
              placeholder="e.g. Upper Deck"
              value={setName}
              onChange={handleFieldChange(setSetName)}
            />
          </div>

          <div className={styles.fieldWrap}>
            <label className={styles.fieldLabel}>Variant / Subset</label>
            <input
              className={styles.fieldInput}
              placeholder="e.g. Young Guns, Prizm"
              value={variant}
              onChange={handleFieldChange(setVariant)}
            />
          </div>
        </div>

        <div className={styles.filterRow}>
          <div className={styles.sportTabs}>
            <button
              className={`${styles.sportTab} ${sport === '' ? styles.sportActive : ''}`}
              onClick={() => { setSport(''); setPage(1) }}
            >All</button>
            {SPORTS.map(s => (
              <button
                key={s}
                className={`${styles.sportTab} ${sport === s ? styles.sportActive : ''}`}
                onClick={() => { setSport(s); setPage(1) }}
              >{s}</button>
            ))}
          </div>
          <label className={styles.checkLabel}>
            <input type="checkbox" checked={isRookie} onChange={e => { setIsRookie(e.target.checked); setPage(1) }} />
            Rookies only
          </label>
        </div>
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

      {!loading && hasSearched && (
        <div className={styles.body}>
          {results.length === 0 ? (
            <div className={styles.empty}>
              <p>No cards found. Try broadening your search.</p>
            </div>
          ) : (
            <>
              <div className={styles.resultMeta}>
                {total != null && <span>{total.toLocaleString()} card{total !== 1 ? 's' : ''} — click one to see its sales</span>}
              </div>
              <div className={styles.cardGrid}>
                {results.map(card => (
                  <button
                    key={card.id}
                    className={styles.cardCard}
                    onClick={() => navigate(`/catalog/${card.id}`)}
                  >
                    <div className={styles.cardPlayer}>
                      {card.player_name}
                      {card.is_rookie && <span className={styles.rcBadge}>RC</span>}
                    </div>
                    <div className={styles.cardDetails}>
                      {card.year} · {card.set_name}
                      {card.variant ? <span className={styles.variant}> · {card.variant}</span> : null}
                    </div>
                    <div className={styles.cardBottom}>
                      <span className={styles.sportChip}>{card.sport}</span>
                      {card.fair_value && (
                        <span className={styles.price}>{fmt(card.fair_value)}</span>
                      )}
                      {card.num_sales && (
                        <span className={styles.salesCount}>{card.num_sales.toLocaleString()} sales</span>
                      )}
                    </div>
                  </button>
                ))}
              </div>

              {totalPages > 1 && (
                <div className={styles.pagination}>
                  <button className={styles.pageBtn} disabled={page <= 1} onClick={() => setPage(p => p - 1)}>← Prev</button>
                  <span className={styles.pageInfo}>Page {page} of {totalPages}</span>
                  <button className={styles.pageBtn} disabled={page >= totalPages} onClick={() => setPage(p => p + 1)}>Next →</button>
                </div>
              )}
            </>
          )}
        </div>
      )}

      {!hasSearched && !loading && (
        <div className={styles.prompt}>
          <p>Search by player name, year, set, or variant to find a card and view its complete sale history.</p>
          <p className={styles.promptHint}>e.g. "McDavid" + "Young Guns" · "Wembanyama" + "Prizm" · "Jordan" + "1986"</p>
        </div>
      )}
    </div>
  )
}
