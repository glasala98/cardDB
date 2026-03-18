import { useState, useEffect, useRef } from 'react'
import { useSearchParams, useNavigate, Link } from 'react-router-dom'
import { getSetDetail } from '../api/catalog'
import styles from './SetDetail.module.css'

const PAGE_SIZE = 100

function fmt(val) {
  if (val == null) return null
  return '$' + Number(val).toLocaleString('en-US', { maximumFractionDigits: 0 })
}

export default function SetDetail() {
  const [searchParams] = useSearchParams()
  const navigate = useNavigate()

  const year    = searchParams.get('year')    ?? ''
  const setName = searchParams.get('set_name') ?? ''

  const [playerSearch, setPlayerSearch] = useState('')
  const [page,         setPage]         = useState(1)
  const [cards,        setCards]        = useState([])
  const [total,        setTotal]        = useState(null)
  const [loading,      setLoading]      = useState(true)
  const [error,        setError]        = useState(null)

  const debounceRef = useRef(null)

  useEffect(() => {
    if (!year || !setName) { setError('Missing year or set name'); setLoading(false); return }
    clearTimeout(debounceRef.current)
    debounceRef.current = setTimeout(() => fetchCards(1), 300)
    return () => clearTimeout(debounceRef.current)
  }, [year, setName, playerSearch])

  async function fetchCards(pg) {
    setLoading(true); setError(null)
    const params = { page: pg, per_page: PAGE_SIZE }
    if (playerSearch) params.search = playerSearch
    try {
      const data = await getSetDetail(year, setName, params)
      setCards(data.cards ?? [])
      setTotal(data.total ?? 0)
      setPage(pg)
    } catch (e) {
      setError(e?.message || 'Failed to load set')
    } finally {
      setLoading(false)
    }
  }

  const totalPages = total != null ? Math.ceil(total / PAGE_SIZE) : 0

  if (error) return (
    <div className={styles.page}>
      <Link to="/sets" className={styles.back}>← Sets</Link>
      <div className={styles.error}>{error}</div>
    </div>
  )

  return (
    <div className={styles.page}>
      <Link to="/sets" className={styles.back}>← Sets</Link>

      <div className={styles.header}>
        <h1 className={styles.setName}>{setName}</h1>
        <div className={styles.setMeta}>
          {year}
          {total != null && <span> · {total.toLocaleString()} cards</span>}
        </div>
      </div>

      <div className={styles.searchRow}>
        <input
          className={styles.playerSearch}
          placeholder="Filter by player…"
          value={playerSearch}
          onChange={e => setPlayerSearch(e.target.value)}
        />
      </div>

      {loading && <div className={styles.status}><span className={styles.spinner} /> Loading…</div>}

      {!loading && (
        <>
          <div className={styles.list}>
            {cards.map((card) => (
              <div key={`${card.card_number}|${card.player_name}`} className={styles.playerRow}>
                <div className={styles.cardNum}>
                  {card.card_number ? `#${card.card_number}` : '—'}
                </div>
                <div className={styles.playerInfo}>
                  <span className={styles.playerName}>{card.player_name}</span>
                  {card.is_rookie && <span className={styles.rcBadge}>RC</span>}
                  {card.team && <span className={styles.team}>{card.team}</span>}
                </div>
                <div className={styles.variantChips}>
                  {(card.variants ?? []).map((v) => (
                    <button
                      key={v.id}
                      className={`${styles.chip} ${v.variant === 'Base' ? styles.chipBase : styles.chipParallel}`}
                      onClick={() => navigate(`/catalog/${v.id}`)}
                      title={v.print_run ? `/${v.print_run}` : undefined}
                    >
                      <span className={styles.chipName}>{v.variant}</span>
                      {v.print_run && <span className={styles.chipPrint}>/{v.print_run}</span>}
                      {v.fair_value && <span className={styles.chipPrice}>{fmt(v.fair_value)}</span>}
                    </button>
                  ))}
                </div>
              </div>
            ))}
          </div>

          {cards.length === 0 && (
            <div className={styles.empty}>No cards found.</div>
          )}

          {totalPages > 1 && (
            <div className={styles.pagination}>
              <button className={styles.pageBtn} disabled={page <= 1} onClick={() => fetchCards(page - 1)}>← Prev</button>
              <span className={styles.pageInfo}>Page {page} of {totalPages}</span>
              <button className={styles.pageBtn} disabled={page >= totalPages} onClick={() => fetchCards(page + 1)}>Next →</button>
            </div>
          )}
        </>
      )}
    </div>
  )
}
