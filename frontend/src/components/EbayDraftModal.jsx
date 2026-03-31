import { useState, useEffect, useRef } from 'react'
import { getEbayStatus, getEbayPrefill, createEbayDraft } from '../api/ebay'
import styles from './EbayDraftModal.module.css'

const CONDITIONS = [
  { id: '2750', label: 'Graded' },
  { id: '3000', label: 'Very Good' },
  { id: '4000', label: 'Good' },
  { id: '5000', label: 'Acceptable' },
]

const AUCTION_DURATIONS = [3, 5, 7, 10]

function getReadiness(form, cardData) {
  if (!form) return []
  const price = parseFloat(form.price)
  return [
    {
      key:      'title',
      label:    'Title',
      required: true,
      ok:       form.title?.trim().length > 0,
    },
    {
      key:      'price',
      label:    form.listing_format === 'AUCTION' ? 'Starting bid' : 'Buy It Now price',
      required: true,
      ok:       price > 0,
      hint:     !price ? 'Enter a price to continue' : null,
    },
    {
      key:      'condition_id',
      label:    'Condition',
      required: true,
      ok:       !!form.condition_id,
    },
    {
      key:      'description',
      label:    'Description',
      required: false,
      ok:       form.description?.trim().length > 20,
      hint:     form.description?.trim().length <= 20 ? 'Short — buyers prefer detail' : null,
    },
    {
      key:      'image',
      label:    'Front photo',
      required: false,
      ok:       !!cardData?.image_url,
      hint:     !cardData?.image_url ? 'No front photo attached' : null,
    },
    {
      key:      'image_back',
      label:    'Back photo',
      required: false,
      ok:       !!cardData?.image_url_back,
      hint:     !cardData?.image_url_back ? 'Upload back of card for better listings' : null,
    },
    {
      key:      'rookie',
      label:    'Rookie flag',
      required: false,
      ok:       cardData?.is_rookie === true,
      hint:     !cardData?.is_rookie ? 'RC not detected — check if applicable' : null,
    },
    {
      key:      'player',
      label:    'Player name',
      required: false,
      ok:       !!cardData?.player_name,
      hint:     !cardData?.player_name ? 'Missing from card data' : null,
    },
    {
      key:      'year',
      label:    'Year / Season',
      required: false,
      ok:       !!cardData?.year,
      hint:     !cardData?.year ? 'Missing from card data' : null,
    },
  ]
}

export default function EbayDraftModal({ cardData, onClose }) {
  const [step, setStep]         = useState('checking')
  const [form, setForm]         = useState(null)
  const [result, setResult]     = useState(null)
  const [errorMsg, setErrorMsg] = useState('')
  const pollRef                 = useRef(null)

  useEffect(() => {
    checkStatus()
    return () => clearInterval(pollRef.current)
  }, [])

  async function checkStatus() {
    try {
      const status = await getEbayStatus()
      if (status.connected) await loadPrefill()
      else setStep('connecting')
    } catch {
      setStep('connecting')
    }
  }

  async function loadPrefill() {
    setStep('checking')
    try {
      const prefill = await getEbayPrefill(cardData.card_name)
      // Merge DB-sourced sport/is_rookie into cardData for the session
      if (prefill.sport)     cardData.sport     = prefill.sport
      if (prefill.is_rookie) cardData.is_rookie = prefill.is_rookie
      setForm({
        title:          prefill.suggested_title || cardData.card_name || '',
        price:          '0.99',
        listing_format: 'AUCTION',
        auction_days:   7,
        condition_id:   prefill.condition_id || (cardData.grade ? '2750' : '3000'),
        description:    prefill.description  || '',
        shipping:       '5.00',
      })
    } catch {
      setForm({
        title:          cardData.card_name || '',
        price:          '0.99',
        listing_format: 'AUCTION',
        auction_days:   7,
        condition_id:   cardData.grade ? '2750' : '3000',
        description:    '',
        shipping:       '5.00',
      })
    }
    setStep('form')
  }

  function openOAuthPopup() {
    const token = localStorage.getItem('auth_token') || ''
    const connectUrl = `/api/ebay/connect${token ? `?token=${encodeURIComponent(token)}` : ''}`
    const popup = window.open(connectUrl, 'ebay_oauth', 'width=620,height=720,scrollbars=yes')
    if (!popup) { window.location.href = connectUrl; return }
    pollRef.current = setInterval(async () => {
      if (popup.closed) {
        clearInterval(pollRef.current)
        try {
          const s = await getEbayStatus()
          if (s.connected) await loadPrefill()
        } catch {}
      }
    }, 1500)
  }

  function setField(key, value) {
    setForm(f => ({ ...f, [key]: value }))
  }

  async function handleSubmit(e) {
    e.preventDefault()
    if (!form.price || parseFloat(form.price) <= 0) {
      setErrorMsg('Price is required.')
      return
    }
    setStep('submitting')
    setErrorMsg('')
    try {
      const res = await createEbayDraft({
        card_name:      cardData.card_name,
        player_name:    cardData.player_name   || '',
        year:           String(cardData.year   || ''),
        brand:          cardData.brand         || '',
        set_name:       cardData.set_name      || '',
        card_number:    cardData.card_number   || '',
        variant:        cardData.variant       || '',
        grade:          cardData.grade         || '',
        serial_number:  cardData.serial_number || '',
        sport:          cardData.sport         || '',
        price:          parseFloat(form.price),
        listing_format: form.listing_format,
        auction_days:   form.listing_format === 'AUCTION' ? form.auction_days : 7,
        condition_id:   form.condition_id,
        description:    form.description,
        image_url:      cardData.image_url      || '',
        image_url_back: cardData.image_url_back || '',
        is_rookie:      cardData.is_rookie      || false,
      })
      setResult(res)
      setStep('success')
    } catch (err) {
      setErrorMsg(err?.response?.data?.detail || err?.message || 'Failed to create draft.')
      setStep('form')
    }
  }

  const readiness    = getReadiness(form, cardData)
  const required     = readiness.filter(r => r.required)
  const optional     = readiness.filter(r => !r.required)
  const requiredDone = required.filter(r => r.ok).length
  const optionalDone = optional.filter(r => r.ok).length
  const allRequired  = requiredDone === required.length
  const totalPct     = Math.round(((requiredDone + optionalDone) / readiness.length) * 100)
  const titleCharsLeft = 80 - (form?.title?.length || 0)
  const isAuction    = form?.listing_format === 'AUCTION'

  return (
    <div className={styles.overlay} onClick={e => e.target === e.currentTarget && onClose()}>
      <div className={styles.modal}>
        <button className={styles.closeBtn} onClick={onClose} aria-label="Close">×</button>

        <div className={styles.header}>
          <span className={styles.ebayLogo}>e<span>b</span><span>a</span><span>y</span></span>
          <h2>Draft Listing</h2>
        </div>

        {step === 'checking' && (
          <div className={styles.center}>
            <div className={styles.spinner} />
            <p>Loading listing details…</p>
          </div>
        )}

        {step === 'connecting' && (
          <div className={styles.center}>
            <p className={styles.connectMsg}>Connect your eBay seller account to create listings.</p>
            <button className={styles.connectBtn} onClick={openOAuthPopup}>Connect eBay Account</button>
            <p className={styles.hint}>A popup will open to authorize. The form loads automatically once connected.</p>
          </div>
        )}

        {step === 'form' && form && (
          <div className={styles.formLayout}>

            <form onSubmit={handleSubmit} className={styles.form}>

              {/* ── Listing type toggle ── */}
              <div className={styles.formatToggle}>
                <button
                  type="button"
                  className={`${styles.formatBtn} ${isAuction ? styles.formatBtnActive : ''}`}
                  onClick={() => setField('listing_format', 'AUCTION')}
                >
                  🔨 Auction
                </button>
                <button
                  type="button"
                  className={`${styles.formatBtn} ${!isAuction ? styles.formatBtnActive : ''}`}
                  onClick={() => setField('listing_format', 'FIXED_PRICE')}
                >
                  🏷️ Buy It Now
                </button>
              </div>

              <div className={styles.fieldGroup}>
                <label className={styles.label}>
                  Title
                  <span className={titleCharsLeft < 10 ? styles.charCountWarn : styles.charCount}>
                    {titleCharsLeft} left
                  </span>
                </label>
                <input
                  className={`${styles.input} ${!form.title ? styles.inputMissing : ''}`}
                  value={form.title}
                  onChange={e => setField('title', e.target.value.slice(0, 80))}
                  maxLength={80}
                  required
                />
              </div>

              <div className={styles.row}>
                <div className={styles.col}>
                  <label className={styles.label}>
                    {isAuction ? 'Starting Bid (CAD)' : 'Price (CAD)'}
                    {!form.price && <span className={styles.requiredBadge}>required</span>}
                  </label>
                  <input
                    className={`${styles.input} ${!form.price ? styles.inputMissing : ''}`}
                    type="number"
                    min="0.01"
                    step="0.01"
                    value={form.price}
                    onChange={e => setField('price', e.target.value)}
                    placeholder={isAuction ? '0.99' : 'Enter price'}
                    required
                  />
                </div>
                <div className={styles.col}>
                  {isAuction ? (
                    <>
                      <label className={styles.label}>Duration</label>
                      <select
                        className={styles.select}
                        value={form.auction_days}
                        onChange={e => setField('auction_days', parseInt(e.target.value))}
                      >
                        {AUCTION_DURATIONS.map(d => (
                          <option key={d} value={d}>{d} days</option>
                        ))}
                      </select>
                    </>
                  ) : (
                    <>
                      <label className={styles.label}>Condition</label>
                      <select
                        className={styles.select}
                        value={form.condition_id}
                        onChange={e => setField('condition_id', e.target.value)}
                      >
                        {CONDITIONS.map(c => (
                          <option key={c.id} value={c.id}>{c.label}</option>
                        ))}
                      </select>
                    </>
                  )}
                </div>
              </div>

              {/* Show condition on its own row for auctions */}
              {isAuction && (
                <div className={styles.fieldGroup}>
                  <label className={styles.label}>Condition</label>
                  <select
                    className={styles.select}
                    value={form.condition_id}
                    onChange={e => setField('condition_id', e.target.value)}
                  >
                    {CONDITIONS.map(c => (
                      <option key={c.id} value={c.id}>{c.label}</option>
                    ))}
                  </select>
                </div>
              )}

              <div className={styles.fieldGroup}>
                <label className={styles.label}>Description</label>
                <textarea
                  className={`${styles.textarea} ${form.description?.trim().length < 20 ? styles.inputWarn : ''}`}
                  value={form.description}
                  onChange={e => setField('description', e.target.value)}
                  rows={4}
                />
              </div>

              <div className={styles.fieldGroup}>
                <label className={styles.label}>Shipping (CAD)</label>
                <input
                  className={styles.input}
                  type="number"
                  min="0"
                  step="0.01"
                  value={form.shipping}
                  onChange={e => setField('shipping', e.target.value)}
                />
              </div>

              {errorMsg && <p className={styles.error}>{errorMsg}</p>}

              <button
                type="submit"
                className={`${styles.submitBtn} ${!allRequired ? styles.submitBtnDisabled : ''}`}
                disabled={!allRequired}
              >
                {allRequired
                  ? `Create ${isAuction ? 'Auction' : 'Buy It Now'} Draft`
                  : `Complete required fields (${requiredDone}/${required.length})`}
              </button>
            </form>

            {/* ── Readiness panel ── */}
            <div className={styles.readinessPanel}>
              <div className={styles.readinessHeader}>
                <span className={styles.readinessTitle}>Readiness</span>
                <span className={`${styles.readinessPct} ${totalPct >= 80 ? styles.pctGood : totalPct >= 50 ? styles.pctMed : styles.pctLow}`}>
                  {totalPct}%
                </span>
              </div>
              <div className={styles.progressBar}>
                <div
                  className={`${styles.progressFill} ${totalPct >= 80 ? styles.fillGood : totalPct >= 50 ? styles.fillMed : styles.fillLow}`}
                  style={{ width: `${totalPct}%` }}
                />
              </div>

              <div className={styles.checkSection}>
                <p className={styles.sectionLabel}>Required</p>
                {required.map(r => <ReadinessRow key={r.key} item={r} />)}
              </div>
              <div className={styles.checkSection}>
                <p className={styles.sectionLabel}>Optional</p>
                {optional.map(r => <ReadinessRow key={r.key} item={r} />)}
              </div>

              <div className={styles.metaSummary}>
                <p className={styles.sectionLabel}>Card Data</p>
                <MetaRow label="Player"  value={cardData.player_name} />
                <MetaRow label="Year"    value={cardData.year} />
                <MetaRow label="Brand"   value={cardData.brand} />
                <MetaRow label="Set"     value={cardData.set_name} />
                <MetaRow label="Variant" value={cardData.variant} />
                <MetaRow label="Grade"   value={cardData.grade} />
                <MetaRow label="Sport"      value={cardData.sport} />
                <MetaRow label="Rookie"     value={cardData.is_rookie ? 'Yes (RC)' : null} />
                <MetaRow label="Front photo" value={cardData.image_url ? '✓' : null} />
                <MetaRow label="Back photo"  value={cardData.image_url_back ? '✓' : null} />
              </div>
            </div>
          </div>
        )}

        {step === 'submitting' && (
          <div className={styles.center}>
            <div className={styles.spinner} />
            <p>Creating draft on eBay…</p>
          </div>
        )}

        {step === 'success' && result && (
          <div className={styles.success}>
            <div className={styles.checkmark}>✓</div>
            <h3>Draft Created!</h3>
            <p>Your listing has been saved as a draft on eBay.</p>
            <a href={result.draft_url} target="_blank" rel="noopener noreferrer" className={styles.reviewBtn}>
              Review & Publish on eBay →
            </a>
            <button className={styles.doneBtn} onClick={onClose}>Done</button>
          </div>
        )}
      </div>
    </div>
  )
}

function ReadinessRow({ item }) {
  const icon = item.ok
    ? <span className={styles.iconOk}>✓</span>
    : item.required
      ? <span className={styles.iconMissing}>✗</span>
      : <span className={styles.iconWarn}>!</span>
  return (
    <div className={styles.readinessRow}>
      {icon}
      <div className={styles.readinessRowText}>
        <span className={item.ok ? styles.rowLabelOk : styles.rowLabel}>{item.label}</span>
        {!item.ok && item.hint && <span className={styles.rowHint}>{item.hint}</span>}
      </div>
    </div>
  )
}

function MetaRow({ label, value }) {
  return (
    <div className={styles.metaRow}>
      <span className={styles.metaLabel}>{label}</span>
      <span className={value ? styles.metaValue : styles.metaEmpty}>{value || '—'}</span>
    </div>
  )
}
