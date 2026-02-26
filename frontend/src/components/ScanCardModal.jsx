import { useState, useRef } from 'react'
import { analyzeCard } from '../api/scan'
import { addCard } from '../api/cards'
import styles from './ScanCardModal.module.css'

export default function ScanCardModal({ onClose, onAdded }) {
  const [frontFile,  setFrontFile]  = useState(null)
  const [backFile,   setBackFile]   = useState(null)
  const [frontPreview, setFrontPreview] = useState(null)
  const [backPreview,  setBackPreview]  = useState(null)
  const [analyzing,  setAnalyzing]  = useState(false)
  const [result,     setResult]     = useState(null)
  const [error,      setError]      = useState(null)

  // Editable form fields (pre-filled by AI or manually entered)
  const [cardName,   setCardName]   = useState('')
  const [costBasis,  setCostBasis]  = useState('')
  const [purchaseDate, setPurchaseDate] = useState('')
  const [tags,       setTags]       = useState('')
  const [saving,     setSaving]     = useState(false)
  const [saved,      setSaved]      = useState(false)

  const frontRef = useRef()
  const backRef  = useRef()

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
    try {
      const data = await analyzeCard(frontFile, backFile)
      setResult(data)
      // Build a card name from the parsed fields
      const parts = [
        data.player_name,
        data.year,
        data.card_set,
        data.subset,
        data.card_number ? `#${data.card_number}` : '',
      ].filter(Boolean)
      setCardName(parts.join(' ').trim())
    } catch (e) {
      setError(e.message || 'Analysis failed')
    } finally {
      setAnalyzing(false)
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
    } catch (e) {
      setError(e.message || 'Save failed')
    } finally {
      setSaving(false)
    }
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

  return (
    <div className={styles.overlay} onClick={e => e.target === e.currentTarget && onClose()}>
      <div className={styles.modal}>
        <div className={styles.header}>
          <h2 className={styles.title}>Scan Card</h2>
          <button className={styles.closeBtn} onClick={onClose}>✕</button>
        </div>

        <div className={styles.body}>
          {/* ── Image upload ── */}
          {!saved && (
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

          {/* ── AI result summary ── */}
          {result && !result.parse_error && (
            <div className={styles.aiResult}>
              <span className={styles.aiTag}>AI identified</span>
              <div className={styles.aiFields}>
                {[
                  ['Player', result.player_name],
                  ['Year', result.year],
                  ['Set', result.card_set],
                  ['Subset', result.subset],
                  ['Card #', result.card_number],
                  ['Team', result.team],
                ].filter(([, v]) => v).map(([k, v]) => (
                  <span key={k} className={styles.aiField}><strong>{k}:</strong> {v}</span>
                ))}
              </div>
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
              placeholder="e.g. Connor McDavid 2015-16 Upper Deck Young Guns #201"
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
              <div className={styles.savedMsg}>✅ Card added! <button className={styles.addAnotherBtn} onClick={() => {
                setSaved(false); setResult(null); setCardName(''); setCostBasis('')
                setPurchaseDate(''); setTags(''); setFrontFile(null); setBackFile(null)
                setFrontPreview(null); setBackPreview(null)
              }}>Add another</button></div>
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
