import { useState, useEffect, useRef } from 'react'
import { getEbayStatus, getEbayPrefill, createEbayDraft } from '../api/ebay'
import styles from './EbayDraftModal.module.css'

const CONDITIONS = [
  { id: '2750', label: 'Graded' },
  { id: '3000', label: 'Very Good' },
  { id: '4000', label: 'Good' },
  { id: '5000', label: 'Acceptable' },
]

// step: 'checking' | 'connecting' | 'form' | 'submitting' | 'success' | 'error'

export default function EbayDraftModal({ cardData, onClose }) {
  const [step, setStep]           = useState('checking')
  const [form, setForm]           = useState(null)
  const [result, setResult]       = useState(null)
  const [errorMsg, setErrorMsg]   = useState('')
  const pollRef                   = useRef(null)

  // On mount: check if eBay is connected
  useEffect(() => {
    checkStatus()
    return () => clearInterval(pollRef.current)
  }, [])

  async function checkStatus() {
    try {
      const status = await getEbayStatus()
      if (status.connected) {
        await loadPrefill()
      } else {
        setStep('connecting')
      }
    } catch {
      setStep('connecting')
    }
  }

  async function loadPrefill() {
    setStep('checking')
    try {
      const prefill = await getEbayPrefill(cardData.card_name)
      setForm({
        title:        prefill.suggested_title || '',
        price:        prefill.suggested_price != null ? String(prefill.suggested_price) : '',
        condition_id: prefill.condition_id || '3000',
        description:  prefill.description || '',
        shipping:     '5.00',
      })
      setStep('form')
    } catch {
      setForm({
        title: cardData.card_name || '',
        price: cardData.fair_value != null ? String(cardData.fair_value) : '',
        condition_id: '3000',
        description: '',
        shipping: '5.00',
      })
      setStep('form')
    }
  }

  function openOAuthPopup() {
    const popup = window.open(
      '/api/ebay/connect',
      'ebay_oauth',
      'width=620,height=720,scrollbars=yes,resizable=yes'
    )
    if (!popup) {
      // Popup blocked — full-page fallback
      window.location.href = '/api/ebay/connect'
      return
    }
    pollRef.current = setInterval(async () => {
      if (popup.closed) {
        clearInterval(pollRef.current)
        // Re-check status after popup closes
        try {
          const status = await getEbayStatus()
          if (status.connected) await loadPrefill()
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
      setErrorMsg('Please enter a listing price.')
      return
    }
    setStep('submitting')
    setErrorMsg('')
    try {
      const res = await createEbayDraft({
        card_name:     cardData.card_name,
        player_name:   cardData.player_name || '',
        year:          String(cardData.year || ''),
        brand:         cardData.brand || '',
        set_name:      cardData.set_name || '',
        card_number:   cardData.card_number || '',
        variant:       cardData.variant || '',
        grade:         cardData.grade || '',
        serial_number: cardData.serial_number || '',
        sport:         cardData.sport || '',
        listing_price: parseFloat(form.price),
        condition_id:  form.condition_id,
        description:   form.description,
        image_url:     cardData.image_url || '',
      })
      setResult(res)
      setStep('success')
    } catch (err) {
      setErrorMsg(err?.response?.data?.detail || err?.message || 'Failed to create draft.')
      setStep('form')
    }
  }

  const titleCharsLeft = 80 - (form?.title?.length || 0)

  return (
    <div className={styles.overlay} onClick={e => e.target === e.currentTarget && onClose()}>
      <div className={styles.modal}>
        <button className={styles.closeBtn} onClick={onClose} aria-label="Close">×</button>
        <div className={styles.header}>
          <span className={styles.ebayLogo}>e<span>b</span><span>a</span><span>y</span></span>
          <h2>Draft Listing</h2>
        </div>

        {/* CHECKING */}
        {step === 'checking' && (
          <div className={styles.center}>
            <div className={styles.spinner} />
            <p>Checking eBay connection…</p>
          </div>
        )}

        {/* CONNECTING */}
        {step === 'connecting' && (
          <div className={styles.center}>
            <p className={styles.connectMsg}>Connect your eBay seller account to create draft listings.</p>
            <button className={styles.connectBtn} onClick={openOAuthPopup}>
              Connect eBay Account
            </button>
            <p className={styles.hint}>A popup will open to authorize access. Once connected, the form will load automatically.</p>
          </div>
        )}

        {/* FORM */}
        {step === 'form' && form && (
          <form onSubmit={handleSubmit} className={styles.form}>
            <label className={styles.label}>
              Title
              <span className={titleCharsLeft < 10 ? styles.charCountWarn : styles.charCount}>
                {titleCharsLeft} chars left
              </span>
            </label>
            <input
              className={styles.input}
              value={form.title}
              onChange={e => setField('title', e.target.value.slice(0, 80))}
              maxLength={80}
              required
            />

            <div className={styles.row}>
              <div className={styles.col}>
                <label className={styles.label}>Price (CAD)</label>
                <input
                  className={styles.input}
                  type="number"
                  min="0.01"
                  step="0.01"
                  value={form.price}
                  onChange={e => setField('price', e.target.value)}
                  placeholder="Enter price"
                  required
                />
              </div>
              <div className={styles.col}>
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
            </div>

            <label className={styles.label}>Description</label>
            <textarea
              className={styles.textarea}
              value={form.description}
              onChange={e => setField('description', e.target.value)}
              rows={4}
            />

            <label className={styles.label}>Shipping cost (CAD)</label>
            <input
              className={styles.input}
              type="number"
              min="0"
              step="0.01"
              value={form.shipping}
              onChange={e => setField('shipping', e.target.value)}
            />

            {errorMsg && <p className={styles.error}>{errorMsg}</p>}

            <button type="submit" className={styles.submitBtn}>
              Create Draft on eBay
            </button>
          </form>
        )}

        {/* SUBMITTING */}
        {step === 'submitting' && (
          <div className={styles.center}>
            <div className={styles.spinner} />
            <p>Creating draft listing on eBay…</p>
          </div>
        )}

        {/* SUCCESS */}
        {step === 'success' && result && (
          <div className={styles.success}>
            <div className={styles.checkmark}>✓</div>
            <h3>Draft Created!</h3>
            <p>Your listing has been saved as a draft on eBay.</p>
            <a
              href={result.draft_url}
              target="_blank"
              rel="noopener noreferrer"
              className={styles.reviewBtn}
            >
              Review & Publish on eBay →
            </a>
            <button className={styles.doneBtn} onClick={onClose}>Done</button>
          </div>
        )}
      </div>
    </div>
  )
}
