import { useState, useRef } from 'react'
import { bulkImport } from '../api/cards'
import styles from './BulkUploadModal.module.css'

export default function BulkUploadModal({ onClose, onImported }) {
  const [file,    setFile]    = useState(null)
  const [result,  setResult]  = useState(null)
  const [loading, setLoading] = useState(false)
  const [error,   setError]   = useState(null)
  const [drag,    setDrag]    = useState(false)
  const inputRef = useRef()

  const handleFile = f => {
    if (f && f.name.endsWith('.csv')) { setFile(f); setError(null); setResult(null) }
    else setError('Please select a .csv file')
  }

  const handleDrop = e => {
    e.preventDefault(); setDrag(false)
    handleFile(e.dataTransfer.files[0])
  }

  const handleSubmit = async () => {
    if (!file) return
    setLoading(true); setError(null)
    try {
      const r = await bulkImport(file)
      setResult(r)
      if (onImported) onImported()
    } catch (e) {
      setError(e.message)
    } finally {
      setLoading(false)
    }
  }

  return (
    <div className={styles.overlay} onClick={e => e.target === e.currentTarget && onClose()}>
      <div className={styles.modal}>
        <div className={styles.header}>
          <h2 className={styles.title}>Bulk Import Cards</h2>
          <button className={styles.closeBtn} onClick={onClose}>✕</button>
        </div>

        <p className={styles.hint}>
          Upload a CSV with a <strong>Card Name</strong> column (required).
          Optional: <em>Cost Basis, Purchase Date, Tags</em>.
        </p>

        {!result ? (
          <>
            <div
              className={`${styles.dropZone} ${drag ? styles.dragOver : ''} ${file ? styles.hasFile : ''}`}
              onDragOver={e => { e.preventDefault(); setDrag(true) }}
              onDragLeave={() => setDrag(false)}
              onDrop={handleDrop}
              onClick={() => inputRef.current?.click()}
            >
              <input
                ref={inputRef}
                type="file"
                accept=".csv"
                style={{ display: 'none' }}
                onChange={e => handleFile(e.target.files[0])}
              />
              {file
                ? <><div className={styles.fileName}>{file.name}</div><div className={styles.fileSize}>{(file.size/1024).toFixed(1)} KB</div></>
                : <><div className={styles.dropIcon}>📄</div><div className={styles.dropText}>Drop CSV here or click to browse</div></>
              }
            </div>

            {error && <p className={styles.error}>{error}</p>}

            <div className={styles.footer}>
              <button className={styles.cancelBtn} onClick={onClose}>Cancel</button>
              <button
                className={styles.importBtn}
                onClick={handleSubmit}
                disabled={!file || loading}
              >
                {loading ? 'Importing…' : 'Import Cards'}
              </button>
            </div>
          </>
        ) : (
          <div className={styles.resultWrap}>
            <div className={styles.resultStat}>
              <span className={styles.resultNum + ' ' + styles.added}>{result.added}</span>
              <span className={styles.resultLabel}>Cards Added</span>
            </div>
            <div className={styles.resultStat}>
              <span className={styles.resultNum + ' ' + styles.skipped}>{result.skipped}</span>
              <span className={styles.resultLabel}>Skipped (existing)</span>
            </div>
            {result.cards?.length > 0 && (
              <ul className={styles.cardList}>
                {result.cards.slice(0, 10).map(c => <li key={c}>{c}</li>)}
                {result.cards.length > 10 && <li className={styles.more}>…and {result.cards.length - 10} more</li>}
              </ul>
            )}
            <div className={styles.footer}>
              <button className={styles.importBtn} onClick={onClose}>Done</button>
            </div>
          </div>
        )}
      </div>
    </div>
  )
}
