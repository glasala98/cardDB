import { useState } from 'react'
import { addCard } from '../api/cards'
import styles from './Modal.module.css'

export default function AddCardModal({ onClose, onAdded }) {
  const [form, setForm] = useState({
    card_name:     '',
    cost_basis:    '',
    purchase_date: '',
    tags:          '',
  })
  const [saving, setSaving] = useState(false)
  const [error,  setError]  = useState(null)

  const set = (key, val) => setForm(f => ({ ...f, [key]: val }))

  const handleAdd = async () => {
    if (!form.card_name.trim()) {
      setError('Card name is required.')
      return
    }
    setSaving(true)
    setError(null)
    try {
      await addCard({
        card_name:     form.card_name.trim(),
        cost_basis:    form.cost_basis !== '' ? Number(form.cost_basis) : 0,
        purchase_date: form.purchase_date || '',
        tags:          form.tags || '',
      })
      onAdded()
    } catch (e) {
      setError(e.message)
      setSaving(false)
    }
  }

  return (
    <div className={styles.overlay} onClick={onClose}>
      <div className={styles.modal} onClick={e => e.stopPropagation()}>
        <div className={styles.header}>
          <h2 className={styles.title}>Add Card</h2>
          <button className={styles.close} onClick={onClose}>✕</button>
        </div>

        <div className={styles.fields}>
          <label className={styles.field}>
            <span className={styles.label}>Card Name <span className={styles.required}>*</span></span>
            <input
              className={styles.input}
              type="text"
              value={form.card_name}
              onChange={e => set('card_name', e.target.value)}
              placeholder="e.g. 2024-25 Upper Deck - Young Guns #201 - Artyom Levshunov"
              autoFocus
            />
            <span className={styles.hint}>Use the full eBay-style card name for best scraping results.</span>
          </label>

          <label className={styles.field}>
            <span className={styles.label}>Cost Basis ($)</span>
            <input
              className={styles.input}
              type="number"
              step="0.01"
              min="0"
              value={form.cost_basis}
              onChange={e => set('cost_basis', e.target.value)}
              placeholder="0.00"
            />
          </label>

          <label className={styles.field}>
            <span className={styles.label}>Purchase Date</span>
            <input
              className={styles.input}
              type="date"
              value={form.purchase_date}
              onChange={e => set('purchase_date', e.target.value)}
            />
          </label>

          <label className={styles.field}>
            <span className={styles.label}>Tags</span>
            <input
              className={styles.input}
              type="text"
              value={form.tags}
              onChange={e => set('tags', e.target.value)}
              placeholder="e.g. rookie, watchlist"
            />
          </label>
        </div>

        {error && <p className={styles.error}>{error}</p>}

        <div className={styles.actions}>
          <button className={styles.cancel} onClick={onClose}>Cancel</button>
          <button className={styles.save} onClick={handleAdd} disabled={saving}>
            {saving ? 'Adding…' : 'Add Card'}
          </button>
        </div>
      </div>
    </div>
  )
}
