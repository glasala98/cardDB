import { useState, useEffect, useRef, useCallback } from 'react'
import { useParams, Link, useNavigate } from 'react-router-dom'
import { getCatalogCard, getCatalogRawSales } from '../api/catalog'
import SourceBadge from '../components/SourceBadge'
import GradeBadge from '../components/GradeBadge'
import styles from './CardSalesPage.module.css'

const PAGE_SIZE = 50

const SOURCES = ['ebay','goldin','heritage','pwcc','fanatics','pristine','myslabs']

function fmt(val) {
  if (val == null) return '—'
  return '$' + Number(val).toLocaleString('en-US', { minimumFractionDigits: 0, maximumFractionDigits: 0 })
}

function fmtDate(d) {
  if (!d) return '—'
  return new Date(d).toLocaleDateString('en-US', { month: 'short', day: 'numeric', year: 'numeric' })
}

// Draw price sparkline on canvas
function drawSparkline(canvas, prices) {
  if (!canvas || prices.length < 2) return
  const ctx  = canvas.getContext('2d')
  const w    = canvas.width
  const h    = canvas.height
  ctx.clearRect(0, 0, w, h)
  const min  = Math.min(...prices)
  const max  = Math.max(...prices)
  const span = max - min || 1
  const pts  = prices.map((p, i) => ({
    x: (i / (prices.length - 1)) * w,
    y: h - ((p - min) / span) * (h - 8) - 4,
  }))
  // Gradient fill
  const grad = ctx.createLinearGradient(0, 0, 0, h)
  grad.addColorStop(0, 'rgba(108,99,255,0.35)')
  grad.addColorStop(1, 'rgba(108,99,255,0)')
  ctx.beginPath()
  ctx.moveTo(pts[0].x, pts[0].y)
  pts.slice(1).forEach(p => ctx.lineTo(p.x, p.y))
  ctx.lineTo(pts[pts.length - 1].x, h)
  ctx.lineTo(pts[0].x, h)
  ctx.closePath()
  ctx.fillStyle = grad
  ctx.fill()
  // Line
  ctx.beginPath()
  ctx.moveTo(pts[0].x, pts[0].y)
  pts.slice(1).forEach(p => ctx.lineTo(p.x, p.y))
  ctx.strokeStyle = '#6c63ff'
  ctx.lineWidth = 2
  ctx.stroke()
}

export default function CardSalesPage() {
  const { id } = useParams()
  const navigate = useNavigate()
  const catalogId = Number(id)

  const [card,    setCard]    = useState(null)
  const [sales,   setSales]   = useState([])
  const [total,   setTotal]   = useState(null)
  const [loading, setLoading] = useState(true)
  const [error,   setError]   = useState(null)
  const [page,    setPage]    = useState(1)
  const [stats,   setStats]   = useState(null)

  const canvasRef = useRef(null)

  const [sources,     setSources]     = useState([])
  const [grade,       setGrade]       = useState('')
  const [serialOnly,  setSerialOnly]  = useState(false)
  const [dateFrom,    setDateFrom]    = useState('')
  const [dateTo,      setDateTo]      = useState('')
  const [priceMin,    setPriceMin]    = useState('')
  const [priceMax,    setPriceMax]    = useState('')
  const [sort,        setSort]        = useState('date_desc')

  // load card info once
  useEffect(() => {
    getCatalogCard(catalogId)
      .then(setCard)
      .catch(() => setError('Card not found'))
  }, [catalogId])

  // load sales when filters/page change
  useEffect(() => {
    setLoading(true)
    setError(null)
    setStats(null)
    const params = {
      limit:  PAGE_SIZE,
      offset: (page - 1) * PAGE_SIZE,
      sort,
    }
    if (sources.length)  params.source     = sources
    if (grade)           params.grade      = grade
    if (serialOnly)      params.serial_only = true
    if (dateFrom)        params.date_from  = dateFrom
    if (dateTo)          params.date_to    = dateTo
    if (priceMin)        params.price_min  = priceMin
    if (priceMax)        params.price_max  = priceMax

    getCatalogRawSales(catalogId, params)
      .then(data => {
        const s = data.sales ?? []
        setSales(s)
        setTotal(data.total ?? 0)
        if (data.stats) setStats(data.stats)
        // Draw sparkline from date-asc prices
        const prices = [...s].reverse().map(r => r.price_val).filter(Boolean)
        setTimeout(() => drawSparkline(canvasRef.current, prices), 0)
      })
      .catch(e => setError(e?.message || 'Failed to load sales'))
      .finally(() => setLoading(false))
  }, [catalogId, sources, grade, serialOnly, dateFrom, dateTo, priceMin, priceMax, sort, page])

  function toggleSource(s) {
    setSources(prev => prev.includes(s) ? prev.filter(x => x !== s) : [...prev, s])
    setPage(1)
  }
  function handleFilterChange(setter) {
    return (e) => { setter(e.target.value); setPage(1) }
  }
  function handleCheckChange(setter) {
    return (e) => { setter(e.target.checked); setPage(1) }
  }

  const totalPages = total != null ? Math.ceil(total / PAGE_SIZE) : 0

  // Stats from API aggregate over full filtered dataset
  const avgPrice  = stats?.avg  ?? null
  const highPrice = stats?.high ?? null
  const lowPrice  = stats?.low  ?? null
  const prices    = sales.map(s => s.price_val).filter(v => v != null && v > 0)

  return (
    <div className={styles.page}>
      <div className={styles.header}>
        <Link to="/search" className={styles.back}>← Search</Link>
        {card ? (
          <div className={styles.cardInfo}>
            <div className={styles.cardTitle}>
              <span className={styles.player}>{card.player_name}</span>
              {card.is_rookie && <span className={styles.rcBadge}>RC</span>}
              {card.scrape_tier === 'staple' && <span className={`${styles.tierBadge} ${styles.staple}`}>Staple</span>}
              {card.scrape_tier === 'premium' && <span className={`${styles.tierBadge} ${styles.premium}`}>Premium</span>}
            </div>
            <div className={styles.cardMeta}>
              {card.year} · {' '}
              <button className={styles.setLink}
                onClick={() => navigate(`/sets/detail?year=${encodeURIComponent(card.year)}&set_name=${encodeURIComponent(card.set_name)}`)}>
                {card.set_name}
              </button>
              {card.variant ? ` · ${card.variant}` : ''}
              {card.card_number ? ` #${card.card_number}` : ''}
            </div>
            {(stats || total > 0) && (
              <div className={styles.statsBar}>
                <div className={styles.stat}><span className={styles.statLabel}>Avg</span><strong>{fmt(avgPrice)}</strong></div>
                <div className={styles.stat}><span className={styles.statLabel}>High</span><strong className={styles.high}>{fmt(highPrice)}</strong></div>
                <div className={styles.stat}><span className={styles.statLabel}>Low</span><strong className={styles.low}>{fmt(lowPrice)}</strong></div>
                <div className={styles.stat}><span className={styles.statLabel}>Sales</span><strong>{total?.toLocaleString()}</strong></div>
                <canvas ref={canvasRef} className={styles.sparkline} width={160} height={40} />
              </div>
            )}
          </div>
        ) : (
          <div className={styles.cardInfo}><span className={styles.loadingText}>Loading…</span></div>
        )}
      </div>

      <div className={styles.body}>
        {/* Filters */}
        <div className={styles.filters}>
          <div className={styles.filterRow}>
            <span className={styles.filterLabel}>Source</span>
            <div className={styles.sourcePills}>
              {SOURCES.map(s => (
                <button
                  key={s}
                  className={`${styles.pill} ${sources.includes(s) ? styles.pillActive : ''}`}
                  onClick={() => toggleSource(s)}
                >
                  <SourceBadge source={s} size="sm" />
                </button>
              ))}
            </div>
          </div>

          <div className={styles.filterRow}>
            <label className={styles.filterLabel}>Grade</label>
            <input
              className={styles.filterInput}
              placeholder="e.g. PSA 10"
              value={grade}
              onChange={handleFilterChange(setGrade)}
            />
            <label className={styles.checkLabel}>
              <input type="checkbox" checked={serialOnly} onChange={handleCheckChange(setSerialOnly)} />
              Numbered only
            </label>
          </div>

          <div className={styles.filterRow}>
            <label className={styles.filterLabel}>Date</label>
            <input type="date" className={styles.filterInput} value={dateFrom} onChange={handleFilterChange(setDateFrom)} />
            <span className={styles.filterSep}>–</span>
            <input type="date" className={styles.filterInput} value={dateTo}   onChange={handleFilterChange(setDateTo)} />
          </div>

          <div className={styles.filterRow}>
            <label className={styles.filterLabel}>Price</label>
            <input className={styles.filterInput} placeholder="Min $" value={priceMin} onChange={handleFilterChange(setPriceMin)} type="number" min="0" />
            <span className={styles.filterSep}>–</span>
            <input className={styles.filterInput} placeholder="Max $" value={priceMax} onChange={handleFilterChange(setPriceMax)} type="number" min="0" />

            <select className={styles.sortSelect} value={sort} onChange={e => { setSort(e.target.value); setPage(1) }}>
              <option value="date_desc">Newest first</option>
              <option value="date_asc">Oldest first</option>
              <option value="price_desc">Price: high → low</option>
              <option value="price_asc">Price: low → high</option>
            </select>
          </div>
        </div>

        {/* Results */}
        {error && <div className={styles.error}>{error}</div>}

        {loading && (
          <div className={styles.status}>
            <span className={styles.spinner} /> Searching…
          </div>
        )}

        {!loading && !error && (
          <>
            <div className={styles.resultCount}>
              {total != null && <span>{total.toLocaleString()} sale{total !== 1 ? 's' : ''}</span>}
            </div>

            {sales.length === 0 ? (
              <div className={styles.empty}>No sales match your filters.</div>
            ) : (
              <div className={styles.table}>
                <div className={styles.tableHead}>
                  <span>Date</span>
                  <span>Source</span>
                  <span>Title</span>
                  <span>Grade</span>
                  <span>Serial</span>
                  <span className={styles.right}>Price</span>
                </div>
                {sales.map((s, i) => (
                  <a
                    key={s.id ?? i}
                    className={`${styles.tableRow} ${s.exclusive ? styles.exclusive : ''}`}
                    href={s.lot_url || undefined}
                    target="_blank"
                    rel="noopener noreferrer"
                    style={s.lot_url ? { cursor: 'pointer' } : { cursor: 'default' }}
                  >
                    <span className={styles.date}>{fmtDate(s.sold_date)}</span>
                    <span><SourceBadge source={s.source} size="sm" /></span>
                    <span className={styles.title}>{s.title}</span>
                    <span>{s.grade ? <GradeBadge grade={s.grade} /> : '—'}</span>
                    <span className={styles.serial}>
                      {s.serial_number && s.print_run ? `#${s.serial_number}/${s.print_run}` : '—'}
                    </span>
                    <span className={`${styles.price} ${styles.right}`}>
                      {fmt(s.price_val)}
                      {s.hammer_price && (
                        <span className={styles.hammer}> (hammer {fmt(s.hammer_price)})</span>
                      )}
                    </span>
                  </a>
                ))}
              </div>
            )}

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
    </div>
  )
}
