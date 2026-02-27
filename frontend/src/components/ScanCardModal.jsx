import { useState, useRef } from 'react'
import { analyzeCard } from '../api/scan'
import { addCard, scrapeCard } from '../api/cards'
import styles from './ScanCardModal.module.css'

// Build structured card name: "YEAR BRAND - SUBSET PARALLEL #NUM - PLAYER [GRADE] #SERIAL"
// This is what parse_card_name() expects for accurate eBay scraping.
function buildCardName(data, serialOverride) {
  const seg1 = [data.year, data.brand].filter(Boolean).join(' ')
  const seg2 = [
    data.subset,
    data.parallel,
    data.card_number ? `#${data.card_number}` : '',
  ].filter(Boolean).join(' ')
  const gradePart  = data.grade ? `[${data.grade}]` : ''
  const serialVal  = (serialOverride || data.serial_number || '').trim()
  const serialPart = serialVal ? `#${serialVal}` : ''
  const seg3 = [data.player_name, gradePart, serialPart].filter(Boolean).join(' ')
  return [seg1, seg2, seg3].filter(Boolean).join(' - ').trim()
}

export default function ScanCardModal({ onClose, onAdded }) {
  const [frontFile,  setFrontFile]  = useState(null)
  const [backFile,   setBackFile]   = useState(null)
  const [frontPreview, setFrontPreview] = useState(null)
  const [backPreview,  setBackPreview]  = useState(null)
  const [analyzing,  setAnalyzing]  = useState(false)
  const [analyzed,   setAnalyzed]   = useState(false)
  const [result,     setResult]     = useState(null)
  const [error,      setError]      = useState(null)

  // Serial override — lets user fill in what the AI missed
  const [serialOverride, setSerialOverride] = useState('')

  // Editable form fields (pre-filled by AI or manually entered)
  const [cardName,   setCardName]   = useState('')
  const [costBasis,  setCostBasis]  = useState('')
  const [purchaseDate, setPurchaseDate] = useState('')
  const [tags,       setTags]       = useState('')
  const [saving,     setSaving]     = useState(false)
  const [saved,      setSaved]      = useState(false)
  const [scraping,   setScraping]   = useState(false)

  const frontRef = useRef()
  const backRef  = useRef()
  // Keep latest result in a ref so serial override handler can access it
  const resultRef = useRef(null)

  const pickFile = (file, setFile, setPreview) => {
    if (!file) return
    setFile(file)
    const reader = new FileReader()
    reader.onload = e => setPreview(e.target.result)
    reader.readAsDataURL(file)
  }

  const handleDrop = (e, setFile, setPreview) => {
    e.preventDefault()
    const file = e.dataTransfer.files[0]
    if (file) pickFile(file, setFile, setPreview)
  }

  const handleAnalyze = async () => {
    if (!frontFile) return
    setAnalyzing(true)
    setError(null)
    setResult(null)
    setSerialOverride('')
    try {
      const data = await analyzeCard(frontFile, backFile)
      resultRef.current = data
      setResult(data)
      setAnalyzed(true)
      if (data.is_sports_card === false) return
      setCardName(buildCardName(data, ''))
    } catch (e) {
      setError(e.message || 'Analysis failed')
    } finally {
      setAnalyzing(false)
    }
  }

  const handleSerialOverride = (val) => {
    setSerialOverride(val)
    if (resultRef.current) {
      setCardName(buildCardName(resultRef.current, val))
    }
  }

  const handleAdd = async () => {
    if (!cardName.trim()) return
    setSaving(true)
    setError(null)
    try {
      await addCard({
        card_name:     cardName.trim(),
        cost_basis:    costBasis ? parseFloat(costBasis) : 0,
        purchase_date: purchaseDate || '',
        tags:          tags || '',
      })
      setSaved(true)
      onAdded?.()
      // Auto-scrape in background — don't await, don't block UI
      setScraping(true)
      scrapeCard(cardName.trim()).finally(() => setScraping(false))
    } catch (e) {
      setError(e.message || 'Save failed')
    } finally {
      setSaving(false)
    }
  }

  const resetAll = () => {
    setSaved(false); setScraping(false); setResult(null); setAnalyzed(false)
    setCardName(''); setCostBasis(''); setPurchaseDate(''); setTags('')
    setFrontFile(null); setBackFile(null)
    setFrontPreview(null); setBackPreview(null)
    setSerialOverride(''); setError(null)
    resultRef.current = null
  }

  const DropZone = ({ label, file, preview, onClick, onDrop }) => (
    <div
      className={`${styles.dropZone} ${file ? styles.hasFile : ''}`}
      onClick={onClick}
      onDrop={onDrop}
      onDragOver={e => e.preventDefault()}
    >
      {preview
        ? <img src={preview} alt={label} className={styles.preview} />
        : (
          <div className={styles.dropPrompt}>
            <span className={styles.dropIcon}>📎</span>
            <span className={styles.dropTitle}>Drag and drop file here</span>
            <span className={styles.dropSub}>Limit 20MB per file • JPG, PNG, WEBP</span>
            <button className={styles.browseBtn} type="button">Browse files</button>
          </div>
        )
      }
    </div>
  )

  const conf = result?.confidence?.toLowerCase()
  const missingBrand  = analyzed && result && !result.parse_error && result.is_sports_card !== false && !result.brand
  const missingSerial = analyzed && result && !result.parse_error && result.is_sports_card !== false && !result.serial_number

  return (
    <div className={styles.overlay} onClick={e => e.target === e.currentTarget && onClose()}>
      <div className={styles.modal}>
        <div className={styles.header}>
          <h2 className={styles.title}>Scan Card</h2>
          <button className={styles.closeBtn} onClick={onClose}>✕</button>
        </div>

        <div className={styles.body}>
          {/* ── Image upload (full) — shown before analysis ── */}
          {!saved && !analyzed && (
            <>
              <div className={styles.uploadSection}>
                <label className={styles.uploadLabel}>Front of card</label>
                <input
                  ref={frontRef}
                  type="file"
                  accept="image/*"
                  style={{ display: 'none' }}
                  onChange={e => pickFile(e.target.files[0], setFrontFile, setFrontPreview)}
                />
                <DropZone
                  label="Front"
                  file={frontFile}
                  preview={frontPreview}
                  onClick={() => frontRef.current.click()}
                  onDrop={e => handleDrop(e, setFrontFile, setFrontPreview)}
                />
              </div>

              <div className={styles.uploadSection}>
                <label className={styles.uploadLabel}>Back of card <span className={styles.optional}>(optional)</span></label>
                <input
                  ref={backRef}
                  type="file"
                  accept="image/*"
                  style={{ display: 'none' }}
                  onChange={e => pickFile(e.target.files[0], setBackFile, setBackPreview)}
                />
                <DropZone
                  label="Back"
                  file={backFile}
                  preview={backPreview}
                  onClick={() => backRef.current.click()}
                  onDrop={e => handleDrop(e, setBackFile, setBackPreview)}
                />
              </div>

              <button
                className={styles.analyzeBtn}
                onClick={handleAnalyze}
                disabled={!frontFile || analyzing}
              >
                {analyzing ? 'Analyzing…' : 'Analyze Card'}
              </button>

              <hr className={styles.divider} />
            </>
          )}

          {/* ── Compact thumbnails — shown after analysis ── */}
          {!saved && analyzed && (
            <div className={styles.analyzedRow}>
              {frontPreview && (
                <div className={styles.analyzedThumb}>
                  <img src={frontPreview} alt="Front" className={styles.thumbImg} />
                  <span className={styles.thumbLabel}>Front</span>
                </div>
              )}
              {backPreview && (
                <div className={styles.analyzedThumb}>
                  <img src={backPreview} alt="Back" className={styles.thumbImg} />
                  <span className={styles.thumbLabel}>Back</span>
                </div>
              )}
              <button className={styles.reanalyzeBtn} onClick={resetAll}>
                ← New scan
              </button>
            </div>
          )}

          {/* ── Not a card error ── */}
          {result && result.is_sports_card === false && (
            <div className={styles.notCardError}>
              <span className={styles.notCardIcon}>⚠️</span>
              <div>
                <strong>Not a sports card</strong>
                <p className={styles.notCardReason}>{result.validation_reason}</p>
              </div>
            </div>
          )}

          {/* ── AI result summary ── */}
          {result && !result.parse_error && result.is_sports_card !== false && (
            <div className={styles.aiResult}>
              <div className={styles.aiResultHeader}>
                <span className={styles.aiTag}>AI identified</span>
                {conf && (
                  <span className={`${styles.confBadge} ${styles[`conf_${conf}`]}`}>
                    {conf} confidence
                  </span>
                )}
              </div>
              <div className={styles.aiFields}>
                {[
                  ['Player',   result.player_name],
                  ['Year',     result.year],
                  ['Brand',    result.brand],
                  ['Subset',   result.subset],
                  ['Parallel', result.parallel],
                  ['Card #',   result.card_number],
                  ['Serial',   result.serial_number],
                  ['Grade',    result.grade],
                ].filter(([, v]) => v).map(([k, v]) => (
                  <span key={k} className={styles.aiField}><strong>{k}:</strong> {v}</span>
                ))}
              </div>

              {/* ── Missing field overrides ── */}
              {(missingBrand || missingSerial) && (
                <div className={styles.missingFields}>
                  <span className={styles.missingLabel}>
                    {missingBrand && missingSerial
                      ? 'Brand and serial not detected — enter below to improve scrape accuracy'
                      : missingBrand
                        ? 'Brand not detected — enter below to improve scrape accuracy'
                        : 'Serial not detected — enter if this card is numbered'}
                  </span>
                  <div className={styles.missingRow}>
                    {missingBrand && (
                      <input
                        className={styles.missingInput}
                        placeholder="Brand (e.g. OPC Platinum)"
                        onChange={e => {
                          if (resultRef.current) {
                            resultRef.current = { ...resultRef.current, brand: e.target.value }
                            setCardName(buildCardName(resultRef.current, serialOverride))
                          }
                        }}
                      />
                    )}
                    {missingSerial && (
                      <input
                        className={styles.missingInput}
                        placeholder="Serial (e.g. 48/199)"
                        value={serialOverride}
                        onChange={e => handleSerialOverride(e.target.value)}
                      />
                    )}
                  </div>
                </div>
              )}

              {cardName && (
                <div className={styles.cardNamePreview}>
                  <span className={styles.cardNamePreviewLabel}>Will be added as</span>
                  <span className={styles.cardNamePreviewValue}>{cardName}</span>
                </div>
              )}
              {conf === 'low' && (
                <p className={styles.confWarning}>Low confidence — please verify all fields before adding.</p>
              )}
              {conf === 'medium' && (
                <p className={styles.confHint}>Medium confidence — review the details below.</p>
              )}
            </div>
          )}

          {result?.parse_error && (
            <div className={styles.aiRaw}>
              <span className={styles.aiTag}>Raw AI output (fill manually below)</span>
              <pre className={styles.rawText}>{result.raw_text}</pre>
            </div>
          )}

          {error && <p className={styles.error}>{error}</p>}

          {/* ── Add New Card form ── */}
          <div className={styles.addSection}>
            <h3 className={styles.addTitle}>Add New Card</h3>

            <label className={styles.fieldLabel}>Card Name *</label>
            <input
              className={styles.input}
              value={cardName}
              onChange={e => setCardName(e.target.value)}
              placeholder="e.g. 2015-16 Upper Deck Series 1 - Young Guns #201 - Connor McDavid"
            />

            <div className={styles.row}>
              <div className={styles.col}>
                <label className={styles.fieldLabel}>Cost Basis ($)</label>
                <input
                  className={styles.input}
                  type="number"
                  step="0.01"
                  min="0"
                  value={costBasis}
                  onChange={e => setCostBasis(e.target.value)}
                  placeholder="0.00"
                />
              </div>
              <div className={styles.col}>
                <label className={styles.fieldLabel}>Purchase Date</label>
                <input
                  className={styles.input}
                  type="date"
                  value={purchaseDate}
                  onChange={e => setPurchaseDate(e.target.value)}
                />
              </div>
            </div>

            <label className={styles.fieldLabel}>Tags</label>
            <input
              className={styles.input}
              value={tags}
              onChange={e => setTags(e.target.value)}
              placeholder="e.g. rookie, graded, watchlist"
            />

            {saved ? (
              <div className={styles.savedMsg}>
                ✅ Card added!{scraping ? ' Scraping eBay…' : ' Scrape complete.'}
                <button className={styles.addAnotherBtn} onClick={resetAll}>Add another</button>
              </div>
            ) : (
              <button
                className={styles.addBtn}
                onClick={handleAdd}
                disabled={!cardName.trim() || saving}
              >
                {saving ? 'Adding…' : '+ Add to Ledger'}
              </button>
            )}
          </div>
        </div>
      </div>
    </div>
  )
}
