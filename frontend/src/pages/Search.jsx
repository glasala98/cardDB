import { useState, useEffect, useRef, useCallback } from 'react'
import { useNavigate } from 'react-router-dom'
import { getCatalog, parseCardQuery } from '../api/catalog'
import styles from './Search.module.css'

const PAGE_SIZE = 30

// ─── Client-side quick parse (instant, no API) ─────────────────────────────
const YEAR_RE    = /\b(20\d{2}(?:-\d{2,4})?|19\d{2}(?:-\d{2})?)\b/
const SPORT_RE   = /\b(NHL|NBA|NFL|MLB)\b/i
const ROOKIE_RE  = /\b(rookie|RC)\b/i

function quickParse(q) {
  let text = q

  const yearM  = text.match(YEAR_RE)
  const year   = yearM ? yearM[1] : ''
  if (yearM) text = text.replace(yearM[0], ' ')

  const sportM = text.match(SPORT_RE)
  const sport  = sportM ? sportM[1].toUpperCase() : ''
  if (sportM) text = text.replace(sportM[0], ' ')

  const isRookie = ROOKIE_RE.test(text)
  text = text.replace(ROOKIE_RE, ' ').replace(/\s+/g, ' ').trim()

  // Put everything else into player_name — AI parse will refine on submit
  return { player_name: text, year, set_name: '', variant: '', sport, is_rookie: isRookie }
}

// ─── Helpers ────────────────────────────────────────────────────────────────
function fmt(val) {
  if (val == null) return null
  return '$' + Number(val).toLocaleString('en-US', { maximumFractionDigits: 0 })
}

const SPORTS = ['NHL', 'NBA', 'NFL', 'MLB']

export default function Search() {
  const navigate = useNavigate()

  // The raw bar text
  const [query, setQuery] = useState('')

  // Structured fields (populated by quick parse + AI parse)
  const [fields, setFields] = useState({
    player_name: '', year: '', set_name: '', variant: '', sport: '', is_rookie: false, card_number: '',
  })

  // Advanced panel open state
  const [advanced, setAdvanced] = useState(false)

  // Results
  const [results,     setResults]     = useState(null)
  const [total,       setTotal]       = useState(null)
  const [loading,     setLoading]     = useState(false)
  const [error,       setError]       = useState(null)
  const [page,        setPage]        = useState(1)
  const [fallbackNote, setFallbackNote] = useState(null)  // what was dropped

  // Parsing state
  const [parsing,  setParsing]  = useState(false)

  const debounceRef  = useRef(null)
  const reqIdRef     = useRef(0)

  // When the bar changes: quick parse → update fields → open advanced if useful
  function handleQueryChange(e) {
    const q = e.target.value
    setQuery(q)
    setPage(1)

    if (!q.trim()) {
      setFields({ player_name: '', year: '', set_name: '', variant: '', sport: '', is_rookie: false, card_number: '' })
      setResults(null); setTotal(null); setError(null)
      return
    }

    const parsed = quickParse(q)
    setFields(f => ({
      ...f,
      player_name: parsed.player_name || f.player_name,
      year:        parsed.year        || f.year,
      sport:       parsed.sport       || f.sport,
      is_rookie:   parsed.is_rookie   !== undefined ? parsed.is_rookie : f.is_rookie,
    }))
  }

  // On Enter or Search button: AI parse → update fields → search
  async function handleSubmit(e) {
    e?.preventDefault()
    if (!query.trim() || query.trim().length < 2) return

    clearTimeout(debounceRef.current)

    // Call AI parse
    if (query.trim().length >= 4) {
      setParsing(true)
      try {
        const parsed = await parseCardQuery(query.trim())
        if (parsed && !parsed.error) {
          setFields({
            player_name: parsed.player_name ?? '',
            year:        parsed.year        ?? '',
            set_name:    parsed.set_name    ?? '',
            variant:     parsed.variant     ?? '',
            sport:       parsed.sport       ?? '',
            is_rookie:   parsed.is_rookie   ?? false,
            card_number: parsed.card_number ?? '',
          })
          setAdvanced(true)
          // Search with AI-parsed fields
          await runSearch({
            player_name: parsed.player_name ?? '',
            year:        parsed.year        ?? '',
            set_name:    parsed.set_name    ?? '',
            variant:     parsed.variant     ?? '',
            sport:       parsed.sport       ?? '',
            is_rookie:   parsed.is_rookie   ?? false,
            card_number: parsed.card_number ?? '',
          }, 1)
          return
        }
      } catch {
        // fall through to quick-parse search
      } finally {
        setParsing(false)
      }
    }

    // Fallback: search with quick-parsed fields
    await runSearch(fields, 1)
  }

  // Field edit in advanced panel → re-search immediately
  const handleFieldEdit = useCallback((key, val) => {
    setFields(f => {
      const next = { ...f, [key]: val }
      setPage(1)
      clearTimeout(debounceRef.current)
      debounceRef.current = setTimeout(() => runSearch(next, 1), 400)
      return next
    })
  }, [])  // eslint-disable-line

  async function runSearch(f, pg) {
    const myId = ++reqIdRef.current

    const hasAny = f.player_name || f.year || f.set_name || f.variant || f.sport || f.is_rookie || f.card_number
    if (!hasAny) { setResults(null); setTotal(null); setFallbackNote(null); return }

    setLoading(true); setError(null); setFallbackNote(null)

    // Build a param object from a filter subset
    function toParams(subset, pageNum) {
      const p = { page: pageNum, per_page: PAGE_SIZE, sort: 'num_sales', dir: 'desc' }
      if (subset.player_name) p.player_name = subset.player_name
      if (subset.year)        p.year        = subset.year
      if (subset.set_name)    p.set_name    = subset.set_name
      if (subset.variant)     p.variant     = subset.variant
      if (subset.sport)       p.sport       = subset.sport
      if (subset.is_rookie)   p.is_rookie   = true
      if (subset.card_number) p.card_number = subset.card_number
      return p
    }

    // Cascade: full → swap set↔variant → drop variant → drop set → player only
    const attempts = [
      { filter: f,                                                                           note: null },
      // If set_name returned nothing, try it as a variant (common misclassification e.g. PMG)
      { filter: { ...f, set_name: '', variant: f.set_name || f.variant },                   note: null },
      { filter: { ...f, variant: '' },                                                       note: f.variant  ? `No exact variant match for "${f.variant}" — dropped it` : null },
      { filter: { ...f, set_name: '', variant: '' },                                         note: f.set_name ? `No results for set "${f.set_name}" — showing all matching cards` : null },
      { filter: { ...f, set_name: '', variant: '', year: '' },                               note: f.year     ? `No exact match — showing all ${f.player_name || 'matching'} cards` : null },
      { filter: { player_name: f.player_name, sport: f.sport },                             note: f.player_name ? `Showing all ${f.player_name} cards` : null },
    ]

    try {
      for (let i = 0; i < attempts.length; i++) {
        const attempt = attempts[i]
        if (myId !== reqIdRef.current) return
        const data = await getCatalog(toParams(attempt.filter, pg))
        if (myId !== reqIdRef.current) return
        const cards = data.cards ?? []
        if (cards.length > 0 || i === attempts.length - 1) {
          setResults(cards)
          setTotal(data.total ?? 0)
          setPage(pg)
          setFallbackNote(attempt.note)
          return
        }
      }
      // All attempts empty
      setResults([])
      setTotal(0)
    } catch (e) {
      if (myId !== reqIdRef.current) return
      setError(e?.message || 'Search failed')
      setResults([])
    } finally {
      if (myId === reqIdRef.current) setLoading(false)
    }
  }

  const totalPages   = total != null ? Math.ceil(total / PAGE_SIZE) : 0
  const hasSearched  = results !== null
  const hasResults   = results?.length > 0

  return (
    <div className={styles.page}>
      <div className={styles.hero}>
        <h1 className={styles.heading}>Card Sales Search</h1>
        <p className={styles.sub}>Find a card to view its complete sale history.</p>

        {/* ── Single smart search bar ── */}
        <form onSubmit={handleSubmit} className={styles.searchForm}>
          <div className={styles.barWrap}>
            <input
              className={styles.bar}
              value={query}
              onChange={handleQueryChange}
              placeholder="e.g. Connor McDavid Red Prizm O-Pee-Chee Platinum 2024"
              autoFocus
            />
            <button type="submit" className={styles.searchBtn} disabled={loading || parsing}>
              {parsing ? '…' : 'Search'}
            </button>
          </div>
          <p className={styles.barHint}>
            Press <kbd>Enter</kbd> to search — we'll figure out the player, set, and variant for you
          </p>
        </form>

        {/* ── Advanced toggle ── */}
        <button
          className={styles.advancedToggle}
          type="button"
          onClick={() => setAdvanced(a => !a)}
        >
          Advanced {advanced ? '▴' : '▾'}
        </button>

        {advanced && (
          <div className={styles.advancedPanel}>
            <div className={styles.advRow}>
              <div className={styles.advField}>
                <label className={styles.advLabel}>Player</label>
                <input
                  className={styles.advInput}
                  placeholder="e.g. Connor McDavid"
                  value={fields.player_name}
                  onChange={e => handleFieldEdit('player_name', e.target.value)}
                />
              </div>
              <div className={styles.advField}>
                <label className={styles.advLabel}>Year</label>
                <input
                  className={styles.advInput}
                  placeholder="e.g. 2024-25"
                  value={fields.year}
                  onChange={e => handleFieldEdit('year', e.target.value)}
                />
              </div>
              <div className={styles.advField}>
                <label className={styles.advLabel}>Card #</label>
                <input
                  className={styles.advInput}
                  placeholder="e.g. 201"
                  value={fields.card_number}
                  onChange={e => handleFieldEdit('card_number', e.target.value)}
                />
              </div>
            </div>
            <div className={styles.advRow}>
              <div className={styles.advField}>
                <label className={styles.advLabel}>Set</label>
                <input
                  className={styles.advInput}
                  placeholder="e.g. O-Pee-Chee Platinum"
                  value={fields.set_name}
                  onChange={e => handleFieldEdit('set_name', e.target.value)}
                />
              </div>
              <div className={styles.advField}>
                <label className={styles.advLabel}>Variant / Subset</label>
                <input
                  className={styles.advInput}
                  placeholder="e.g. Red Prizm, Young Guns"
                  value={fields.variant}
                  onChange={e => handleFieldEdit('variant', e.target.value)}
                />
              </div>
            </div>
            <div className={styles.advRow}>
              <div className={styles.advField}>
                <label className={styles.advLabel}>Sport</label>
                <div className={styles.sportTabs}>
                  <button type="button"
                    className={`${styles.sportTab} ${fields.sport === '' ? styles.sportActive : ''}`}
                    onClick={() => handleFieldEdit('sport', '')}
                  >All</button>
                  {SPORTS.map(s => (
                    <button type="button" key={s}
                      className={`${styles.sportTab} ${fields.sport === s ? styles.sportActive : ''}`}
                      onClick={() => handleFieldEdit('sport', s)}
                    >{s}</button>
                  ))}
                </div>
              </div>
              <label className={styles.checkLabel}>
                <input
                  type="checkbox"
                  checked={fields.is_rookie}
                  onChange={e => handleFieldEdit('is_rookie', e.target.checked)}
                />
                Rookies only
              </label>
            </div>
          </div>
        )}
      </div>

      {/* ── Status ── */}
      {(loading || parsing) && (
        <div className={styles.statusRow}>
          <span className={styles.spinner} />
          <span>{parsing ? 'Parsing query…' : 'Searching…'}</span>
        </div>
      )}

      {error && !loading && (
        <div className={styles.error}>{error}</div>
      )}

      {/* ── Results ── */}
      {!loading && !parsing && hasSearched && (
        <div className={styles.body}>
          {!hasResults ? (
            <div className={styles.empty}>
              No cards found. Try adjusting your search or opening Advanced to refine.
            </div>
          ) : (
            <>
              <div className={styles.resultMeta}>
                {fallbackNote && (
                  <div className={styles.fallbackNote}>⚠ {fallbackNote}</div>
                )}
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
                    {card.card_number && (
                      <div className={styles.cardNum}>#{card.card_number}</div>
                    )}
                    <div className={styles.cardBottom}>
                      <span className={styles.sportChip}>{card.sport}</span>
                      {card.fair_value && <span className={styles.price}>{fmt(card.fair_value)}</span>}
                      {card.num_sales  && <span className={styles.salesCount}>{card.num_sales.toLocaleString()} sales</span>}
                    </div>
                  </button>
                ))}
              </div>

              {totalPages > 1 && (
                <div className={styles.pagination}>
                  <button className={styles.pageBtn} disabled={page <= 1} onClick={() => runSearch(fields, page - 1)}>← Prev</button>
                  <span className={styles.pageInfo}>Page {page} of {totalPages}</span>
                  <button className={styles.pageBtn} disabled={page >= totalPages} onClick={() => runSearch(fields, page + 1)}>Next →</button>
                </div>
              )}
            </>
          )}
        </div>
      )}

      {!hasSearched && !loading && !parsing && (
        <div className={styles.prompt}>
          <p>Type a player, set, year, variant — or any combination — and hit Search.</p>
          <p className={styles.promptHint}>
            "McDavid Young Guns 2015" · "Wembanyama Prizm RC" · "Jordan 1986 Fleer"
          </p>
        </div>
      )}
    </div>
  )
}
