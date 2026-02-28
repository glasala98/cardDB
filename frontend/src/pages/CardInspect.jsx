import { useState, useEffect } from 'react'
import { useParams, Link } from 'react-router-dom'
import PriceChart from '../components/PriceChart'
import ConfidenceBadge from '../components/ConfidenceBadge'
import TrendBadge from '../components/TrendBadge'
import { getCardDetail, scrapeCard, updateCard, fetchImage } from '../api/cards'
import { getGradingLookup } from '../api/masterDb'
import { useCurrency } from '../context/CurrencyContext'
import CurrencySelect from '../components/CurrencySelect'
import pageStyles from './Page.module.css'
import styles from './CardInspect.module.css'

export default function CardInspect() {
  const { cardName } = useParams()
  const name = decodeURIComponent(cardName)

  const [data,     setData]     = useState(null)
  const [loading,  setLoading]  = useState(true)
  const [error,    setError]    = useState(null)
  const [scraping, setScraping] = useState(false)
  const [toast,    setToast]    = useState(null)

  // Grading ROI — costs hardcoded to current standard-tier pricing (2025)
  const GRADING_COSTS = { psa: 25, bgs: 150, tag: 20 }
  const [gradingData,   setGradingData]   = useState(null)
  const [gradingResult, setGradingResult] = useState(null)

  // Price override (for "not found" cards)
  const [overrideVal,     setOverrideVal]     = useState('')
  const [overrideSaving,  setOverrideSaving]  = useState(false)

  const [imageUrl,     setImageUrl]     = useState(null)
  const [imageUrlBack, setImageUrlBack] = useState(null)
  const [flipped,      setFlipped]      = useState(false)
  const [fetchingImg,  setFetchingImg]  = useState(false)

  const load = () => {
    setLoading(true)
    getCardDetail(name)
      .then(d => {
        setData(d)
        setImageUrl(d.image_url || null)
        setImageUrlBack(d.image_url_back || null)
        setFlipped(false)
        // Auto-fetch images from eBay listing if not stored
        if ((!d.image_url || !d.image_url_back) && d.raw_sales?.some(s => s.listing_url)) {
          setFetchingImg(true)
          fetchImage(name)
            .then(r => {
              setImageUrl(r.image_url || null)
              setImageUrlBack(r.image_url_back || null)
            })
            .catch(() => {})
            .finally(() => setFetchingImg(false))
        }
        // Auto-fetch grading data and compute ROI with hardcoded costs
        const player = d?.card?.player
        if (player) {
          getGradingLookup(player)
            .then(r => {
              const cards = r.cards || []
              setGradingData(cards)
              const raw = d?.card?.fair_value ?? 0
              const m = cards?.[0]
              const { psa, bgs, tag } = { psa: 25, bgs: 150, tag: 20 }
              setGradingResult({
                raw,
                psa: {
                  fee:  psa,
                  gr9:  { price: m?.psa9_price  ?? 0, roi: (m?.psa9_price  ?? 0) - raw - psa },
                  gr10: { price: m?.psa10_price ?? 0, roi: (m?.psa10_price ?? 0) - raw - psa },
                },
                bgs: {
                  fee:  bgs,
                  gr95: { price: m?.bgs95_price ?? 0, roi: (m?.bgs95_price ?? 0) - raw - bgs },
                  gr10: { price: m?.bgs10_price ?? 0, roi: (m?.bgs10_price ?? 0) - raw - bgs },
                },
                tag: { fee: tag },
              })
            })
            .catch(() => {})
        }
      })
      .catch(e => setError(e.message))
      .finally(() => setLoading(false))
  }
  useEffect(load, [name])

  const showToast = (msg, type = 'success') => {
    setToast({ msg, type })
    setTimeout(() => setToast(null), 3500)
  }


  const handlePriceOverride = async () => {
    const val = parseFloat(overrideVal)
    if (!val || val <= 0) return
    setOverrideSaving(true)
    try {
      await updateCard(name, { fair_value: val })
      showToast(`Price set to $${val.toFixed(2)}`)
      load()
    } catch (e) {
      showToast(e.message, 'error')
    } finally {
      setOverrideSaving(false)
    }
  }

  const handleScrape = async () => {
    setScraping(true)
    try {
      await scrapeCard(name)
      showToast('Scrape queued — refresh in ~30s to see updated price')
    } catch (e) {
      showToast(e.message, 'error')
    } finally {
      setScraping(false)
    }
  }

  if (loading) return <p className={pageStyles.status}>Loading…</p>
  if (error)   return <p className={pageStyles.error}>Error: {error}</p>
  if (!data)   return <p className={pageStyles.status}>Card not found.</p>

  const { card, price_history, raw_sales, confidence, search_url, is_estimated, price_source } = data

  const { fmtPrice } = useCurrency()
  const gain     = (card.fair_value ?? 0) - (card.cost_basis ?? 0)
  const hasValue = card.fair_value != null && card.fair_value > 0
  const hasCost  = card.cost_basis != null && card.cost_basis > 0
  const fmt      = v => fmtPrice(v)

  const priceTier = (() => {
    const v = card.fair_value ?? 0
    if (v >= 100) return { label: 'GOLD',   cls: styles.tierGold }
    if (v >= 25)  return { label: 'SILVER', cls: styles.tierSilver }
    if (v >= 10)  return { label: 'BRONZE', cls: styles.tierBronze }
    return null
  })()

  return (
    <div className={pageStyles.page}>

      {toast && <div className={`${styles.toast} ${styles[toast.type]}`}>{toast.msg}</div>}

      <div className={styles.topBar}>
        <Link to="/ledger" className={styles.back}>← Back to Ledger</Link>
        <CurrencySelect />
      </div>

      <div className={styles.cardHeader}>
        <div className={styles.cardImageWrap}>
          {imageUrl ? (
            <div
              className={`${styles.cardFlipper} ${flipped ? styles.flipped : ''} ${imageUrlBack ? styles.cardFlippable : ''}`}
              onClick={() => imageUrlBack && setFlipped(f => !f)}
              title={imageUrlBack ? (flipped ? 'Click to see front' : 'Click to see back') : undefined}
            >
              <div className={styles.cardFront}>
                <img src={imageUrl} alt={name}
                  onError={e => { e.currentTarget.style.display = 'none' }} />
                {imageUrlBack && !flipped && (
                  <span className={styles.flipHint}>flip ↻</span>
                )}
              </div>
              {imageUrlBack && (
                <div className={styles.cardBackFace}>
                  <img src={imageUrlBack} alt={`${name} back`}
                    onError={e => { e.currentTarget.style.display = 'none' }} />
                  {flipped && (
                    <span className={styles.flipHint}>flip ↺</span>
                  )}
                </div>
              )}
            </div>
          ) : (
            <div className={styles.cardImagePlaceholder}>
              {fetchingImg ? 'Loading image…' : 'No image available'}
            </div>
          )}
        </div>
        <div className={styles.titleRow}>
          <h1 className={styles.cardTitle}>{name}</h1>
          <div className={styles.headerActions}>
            <ConfidenceBadge confidence={confidence} />
            {priceTier && (
              <span className={`${styles.tierBadge} ${priceTier.cls}`}>{priceTier.label}</span>
            )}
            <button
              className={styles.scrapeBtn}
              onClick={handleScrape}
              disabled={scraping}
            >
              {scraping ? 'Queuing…' : '⟳ Rescrape'}
            </button>
            {search_url && (
              <a
                href={search_url}
                target="_blank"
                rel="noopener noreferrer"
                className={styles.ebayLink}
              >
                View on eBay ↗
              </a>
            )}
          </div>
        </div>
        {card.last_scraped && (
          <p className={styles.lastScraped}>Last scraped: {card.last_scraped}</p>
        )}
      </div>

      {/* ── Metrics ── */}
      <div className={styles.metrics}>
        <MetricCard
          label="Fair Value"
          value={fmt(card.fair_value)}
          large
          estimated={is_estimated}
          priceSource={price_source}
        />
        <MetricCard label="Cost Basis" value={fmt(card.cost_basis)} />
        {hasCost && hasValue && (
          <MetricCard
            label="Gain / Loss"
            value={`${gain >= 0 ? '+' : ''}${fmt(gain)}`}
            color={gain >= 0 ? 'success' : 'danger'}
          />
        )}
        <MetricCard label="Trend"  value={<TrendBadge trend={card.trend} />} />
        <MetricCard label="Sales"  value={card.num_sales || '—'} />
        <MetricCard label="Median" value={fmt(card.median_all)} />
        <MetricCard label="Min"    value={fmt(card.min)} />
        <MetricCard label="Max"    value={fmt(card.max)} />
        {card.purchase_date && (
          <MetricCard label="Purchased" value={card.purchase_date} />
        )}
      </div>

      {card.top3 && (
        <p className={styles.top3}>
          <span className={styles.top3Label}>Top 3 recent:</span> {card.top3}
        </p>
      )}

      {/* ── Price Override (not-found cards) ── */}
      {(confidence === 'not found' || confidence === 'notfound') && (
        <div className={styles.section}>
          <div className={styles.sectionHeader}>
            <h2 className={styles.sectionTitle}>Manual Price Override</h2>
          </div>
          <p className={styles.overrideNote}>
            This card wasn't found on eBay. You can set a manual fair value.
          </p>
          <div className={styles.overrideRow}>
            <input
              type="number"
              min="0"
              step="0.01"
              placeholder="Enter price (CAD)"
              value={overrideVal}
              onChange={e => setOverrideVal(e.target.value)}
              className={styles.overrideInput}
            />
            <button
              className={styles.overrideBtn}
              onClick={handlePriceOverride}
              disabled={overrideSaving || !overrideVal}
            >
              {overrideSaving ? 'Saving…' : 'Set Price'}
            </button>
          </div>
        </div>
      )}

      {/* ── Grading ROI Calculator — hidden for already-graded cards ── */}
      {gradingResult && !data?.card?.grade && (
        <div className={styles.section}>
          <div className={styles.sectionHeader}>
            <h2 className={styles.sectionTitle}>Grading ROI Calculator</h2>
          </div>
          <div className={styles.roiResults}>
            {/* Header */}
            <div className={`${styles.roiRow} ${styles.roiHeader}`}>
              <span className={styles.roiGrade}>Service</span>
              <span className={styles.roiFee}>Fee</span>
              <span className={styles.roiPrice}>Market Value</span>
              <span className={styles.roiChange}>ROI</span>
            </div>
            {/* Raw baseline */}
            <div className={styles.roiRow}>
              <span className={styles.roiGrade}>Raw</span>
              <span className={styles.roiFee}>—</span>
              <span className={styles.roiPrice}>{fmt(gradingResult.raw)}</span>
              <span className={styles.roiChange}>—</span>
            </div>
            {/* PSA rows */}
            {gradingResult.psa.gr9.price > 0 && (
              <div className={`${styles.roiRow} ${gradingResult.psa.gr9.roi > 0 ? styles.roiPositive : styles.roiNegative}`}>
                <span className={styles.roiGrade}>PSA 9</span>
                <span className={styles.roiFee}>{fmt(gradingResult.psa.fee)}</span>
                <span className={styles.roiPrice}>{fmt(gradingResult.psa.gr9.price)}</span>
                <span className={styles.roiChange}>{gradingResult.psa.gr9.roi >= 0 ? '+' : ''}{fmt(gradingResult.psa.gr9.roi)}</span>
              </div>
            )}
            {gradingResult.psa.gr10.price > 0 && (
              <div className={`${styles.roiRow} ${gradingResult.psa.gr10.roi > 0 ? styles.roiPositive : styles.roiNegative}`}>
                <span className={styles.roiGrade}>PSA 10</span>
                <span className={styles.roiFee}>{fmt(gradingResult.psa.fee)}</span>
                <span className={styles.roiPrice}>{fmt(gradingResult.psa.gr10.price)}</span>
                <span className={styles.roiChange}>{gradingResult.psa.gr10.roi >= 0 ? '+' : ''}{fmt(gradingResult.psa.gr10.roi)}</span>
              </div>
            )}
            {/* BGS rows */}
            {gradingResult.bgs.gr95.price > 0 && (
              <div className={`${styles.roiRow} ${gradingResult.bgs.gr95.roi > 0 ? styles.roiPositive : styles.roiNegative}`}>
                <span className={styles.roiGrade}>BGS 9.5</span>
                <span className={styles.roiFee}>{fmt(gradingResult.bgs.fee)}</span>
                <span className={styles.roiPrice}>{fmt(gradingResult.bgs.gr95.price)}</span>
                <span className={styles.roiChange}>{gradingResult.bgs.gr95.roi >= 0 ? '+' : ''}{fmt(gradingResult.bgs.gr95.roi)}</span>
              </div>
            )}
            {gradingResult.bgs.gr10.price > 0 && (
              <div className={`${styles.roiRow} ${gradingResult.bgs.gr10.roi > 0 ? styles.roiPositive : styles.roiNegative}`}>
                <span className={styles.roiGrade}>BGS 10</span>
                <span className={styles.roiFee}>{fmt(gradingResult.bgs.fee)}</span>
                <span className={styles.roiPrice}>{fmt(gradingResult.bgs.gr10.price)}</span>
                <span className={styles.roiChange}>{gradingResult.bgs.gr10.roi >= 0 ? '+' : ''}{fmt(gradingResult.bgs.gr10.roi)}</span>
              </div>
            )}
            {/* TAG row — no market data available */}
            <div className={styles.roiRow}>
              <span className={styles.roiGrade}>TAG</span>
              <span className={styles.roiFee}>{fmt(gradingResult.tag.fee)}</span>
              <span className={styles.roiPrice} style={{ color: 'var(--text-secondary)' }}>No data</span>
              <span className={styles.roiChange}>—</span>
            </div>
            {/* No graded data message */}
            {gradingResult.psa.gr9.price === 0 && gradingResult.psa.gr10.price === 0 &&
             gradingResult.bgs.gr95.price === 0 && gradingResult.bgs.gr10.price === 0 && (
              <p className={styles.roiEmpty}>No PSA/BGS market data for this card in the Young Guns DB.</p>
            )}
            {/* Verdict */}
            {(() => {
              const best = Math.max(
                gradingResult.psa.gr10.roi, gradingResult.psa.gr9.roi,
                gradingResult.bgs.gr10.roi, gradingResult.bgs.gr95.roi
              )
              if (best > 20) return (
                <p className={`${styles.roiVerdict} ${styles.roiWorthIt}`}>
                  Worth grading — best ROI is {fmt(best)} after fees.
                </p>
              )
              if (best > 0) return (
                <p className={`${styles.roiVerdict} ${styles.roiMarginal}`}>
                  Marginal gain — may be worth it for gem-mint candidates.
                </p>
              )
              if (gradingResult.psa.gr10.price > 0 || gradingResult.bgs.gr10.price > 0) return (
                <p className={`${styles.roiVerdict} ${styles.roiNotWorth}`}>
                  Not profitable after grading fees.
                </p>
              )
              return null
            })()}
          </div>
        </div>
      )}

      {/* ── Price History Chart ── */}
      <div className={styles.section}>
        <PriceChart data={price_history || []} title="Price History" />
      </div>

      {/* ── Sales Table ── */}
      <div className={styles.section}>
        <div className={styles.sectionHeader}>
          <h2 className={styles.sectionTitle}>Sales History</h2>
          <span className={styles.sectionCount}>{raw_sales.length} records</span>
        </div>

        {raw_sales.length === 0 ? (
          <p className={styles.empty}>No direct sales on record yet.</p>
        ) : (
          <div className={styles.salesWrap}>
            <table className={styles.salesTable}>
              <thead>
                <tr>
                  <th className={styles.th}>Date</th>
                  <th className={styles.th}>Price</th>
                  <th className={styles.th}>Title</th>
                </tr>
              </thead>
              <tbody>
                {raw_sales.map((s, i) => (
                  <tr key={i} className={styles.salesRow}>
                    <td className={`${styles.td} ${styles.dateCell}`}>{s.sold_date || '—'}</td>
                    <td className={`${styles.td} ${styles.priceCell}`}>
                      {s.price != null ? fmtPrice(s.price) : '—'}
                    </td>
                    <td className={`${styles.td} ${styles.titleCell}`}>
                      {s.listing_url ? (
                        <a href={s.listing_url} target="_blank" rel="noopener noreferrer" className={styles.saleLink}>
                          {s.title}
                        </a>
                      ) : s.title}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>
    </div>
  )
}

const PRICE_SOURCE_LABEL = {
  raw_estimate:       '~Est. from raw',
  raw_estimate_psa10: '~Est. raw ×2.5',
  psa9_estimate:      '~Est. PSA 9 ×2.5',
}

function MetricCard({ label, value, large, color, estimated, priceSource }) {
  const colorClass = color === 'success' ? styles.success : color === 'danger' ? styles.danger : ''
  return (
    <div className={styles.metric}>
      <span className={styles.metricLabel}>
        {label}
        {estimated && (
          <span className={styles.estBadge} title={PRICE_SOURCE_LABEL[priceSource] || 'Estimated value — no direct comps found'}>
            ~Est.
          </span>
        )}
      </span>
      <span className={`${styles.metricValue} ${large ? styles.large : ''} ${colorClass}`}>
        {value}
      </span>
    </div>
  )
}
