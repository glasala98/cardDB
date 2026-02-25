import { useState } from 'react'
import { updateCard } from '../api/cards'
import styles from './Modal.module.css'

export default function EditCardModal({ card, onClose, onSaved }) {
  const [form, setForm] = useState({
    fair_value:    card.fair_value    ?? '',
    cost_basis:    card.cost_basis    ?? '',
    purchase_date: card.purchase_date ?? '',
    tags:          card.tags          ?? '',
  })
  const [saving, setSaving] = useState(false)
  const [error, setError]   = useState(null)

  const set = (key, val) => setForm(f => ({ ...f, [key]: val }))

  const handleSave = async () => {
    setSaving(true)
    setError(null)
    try {
      const body = {
        fair_value:    form.fair_value    !== '' ? Number(form.fair_value)    : null,
        cost_basis:    form.cost_basis    !== '' ? Number(form.cost_basis)    : null,
        purchase_date: form.purchase_date || null,
        tags:          form.tags          ?? null,
      }
      await updateCard(card.card_name, body)
      onSaved()
    } catch (e) {
      setError(e.message)
      setSaving(false)
    }
  }

  return (
    <div className={styles.overlay} onClick={onClose}>
      <div className={styles.modal} onClick={e => e.stopPropagation()}>
        <div className={styles.header}>
          <h2 className={styles.title}>Edit Card</h2>
          <button className={styles.close} onClick={onClose}>✕</button>
        </div>

        <p className={styles.cardName}>{card.card_name}</p>

        <div className={styles.fields}>
          <label className={styles.field}>
            <span className={styles.label}>Fair Value ($)</span>
            <input
              className={styles.input}
              type="number"
              step="0.01"
              min="0"
              value={form.fair_value}
              onChange={e => set('fair_value', e.target.value)}
              placeholder="0.00"
            />
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
              placeholder="e.g. rookie, graded, watchlist"
            />
          </label>
        </div>

        {error && <p className={styles.error}>{error}</p>}

        <div className={styles.actions}>
          <button className={styles.cancel} onClick={onClose}>Cancel</button>
          <button className={styles.save} onClick={handleSave} disabled={saving}>
            {saving ? 'Saving…' : 'Save Changes'}
          </button>
        </div>
      </div>
    </div>
  )
}
