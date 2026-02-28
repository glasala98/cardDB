import { useState, useEffect } from 'react'
import ConfirmDialog from '../components/ConfirmDialog'
import { getArchive, restoreCard } from '../api/cards'
import styles from './Archive.module.css'
import pageStyles from './Page.module.css'

export default function Archive() {
  const [cards,   setCards]   = useState([])
  const [loading, setLoading] = useState(true)
  const [error,   setError]   = useState(null)
  const [search,  setSearch]  = useState('')
  const [restoreTarget, setRestoreTarget] = useState(null)
  const [toast,   setToast]   = useState(null)
  const [selected, setSelected] = useState(new Set())
  const [bulkRestoring, setBulkRestoring] = useState(false)

  const load = () => {
    setLoading(true)
    getArchive()
      .then(data => { setCards(data.cards || []); setError(null) })
      .catch(e => setError(e.message))
      .finally(() => setLoading(false))
  }
  useEffect(load, [])

  const showToast = (msg, type = 'success') => {
    setToast({ msg, type })
    setTimeout(() => setToast(null), 3500)
  }

  const handleRestore = async () => {
    try {
      await restoreCard(restoreTarget)
      setCards(prev => prev.filter(c => c.card_name !== restoreTarget))
      showToast(`"${restoreTarget}" restored to ledger`)
    } catch (e) {
      showToast(e.message, 'error')
    } finally {
      setRestoreTarget(null)
    }
  }

  const filtered = cards.filter(c =>
    !search || c.card_name?.toLowerCase().includes(search.toLowerCase())
  )

  const allSelected = filtered.length > 0 && filtered.every(c => selected.has(c.card_name))

  const toggleSelectAll = () => {
    if (allSelected) {
      setSelected(prev => {
        const next = new Set(prev)
        filtered.forEach(c => next.delete(c.card_name))
        return next
      })
    } else {
      setSelected(prev => {
        const next = new Set(prev)
        filtered.forEach(c => next.add(c.card_name))
        return next
      })
    }
  }

  const toggleRow = (name) => {
    setSelected(prev => {
      const next = new Set(prev)
      next.has(name) ? next.delete(name) : next.add(name)
      return next
    })
  }

  const handleBulkRestore = async () => {
    setBulkRestoring(true)
    const names = [...selected].filter(n => cards.some(c => c.card_name === n))
    let restored = 0
    let failed = 0
    for (const name of names) {
      try {
        await restoreCard(name)
        restored++
      } catch {
        failed++
      }
    }
    setCards(prev => prev.filter(c => !selected.has(c.card_name)))
    setSelected(new Set())
    setBulkRestoring(false)
    if (failed === 0) showToast(`${restored} card${restored !== 1 ? 's' : ''} restored`)
    else showToast(`${restored} restored, ${failed} failed`, 'error')
  }

  return (
    <div className={pageStyles.page}>

      {toast && <div className={`${styles.toast} ${styles[toast.type]}`}>{toast.msg}</div>}

      <div className={pageStyles.header}>
        <h1 className={pageStyles.title}>Archive</h1>
        <span className={pageStyles.count}>{cards.length} cards</span>
      </div>

      <p className={styles.subtitle}>
        Archived cards are removed from the ledger but kept here. Restore them to bring them back.
      </p>

      <div className={pageStyles.toolbar}>
        <input
          className={pageStyles.search}
          placeholder="Search archived cards…"
          value={search}
          onChange={e => setSearch(e.target.value)}
        />
        {selected.size > 0 && (
          <button
            className={styles.bulkRestoreBtn}
            onClick={handleBulkRestore}
            disabled={bulkRestoring}
          >
            {bulkRestoring ? 'Restoring…' : `↩ Restore Selected (${selected.size})`}
          </button>
        )}
      </div>

      {loading && <p className={pageStyles.status}>Loading…</p>}
      {error   && <p className={pageStyles.error}>Error: {error}</p>}

      {!loading && !error && filtered.length === 0 && (
        <p className={pageStyles.status}>
          {cards.length === 0 ? 'No archived cards.' : 'No cards match your search.'}
        </p>
      )}

      {!loading && !error && filtered.length > 0 && (
        <div className={styles.tableWrap}>
          <table className={styles.table}>
            <thead>
              <tr>
                <th className={`${styles.th} ${styles.checkCol}`}>
                  <input
                    type="checkbox"
                    checked={allSelected}
                    onChange={toggleSelectAll}
                    className={styles.checkbox}
                    title="Select all"
                  />
                </th>
                <th className={styles.th}>Card Name</th>
                <th className={styles.th}>Archived Date</th>
                <th className={styles.th}>Last Value</th>
                <th className={styles.th}>Actions</th>
              </tr>
            </thead>
            <tbody>
              {filtered.map(card => (
                <tr
                  key={card.card_name}
                  className={`${styles.tr} ${selected.has(card.card_name) ? styles.trSelected : ''}`}
                >
                  <td className={`${styles.td} ${styles.checkCol}`}>
                    <input
                      type="checkbox"
                      checked={selected.has(card.card_name)}
                      onChange={() => toggleRow(card.card_name)}
                      className={styles.checkbox}
                    />
                  </td>
                  <td className={`${styles.td} ${styles.nameCell}`}>{card.card_name}</td>
                  <td className={styles.td}>{card.archived_date || '—'}</td>
                  <td className={styles.td}>
                    {card.fair_value ? `$${Number(card.fair_value).toFixed(2)}` : '—'}
                  </td>
                  <td className={styles.td}>
                    <button
                      className={styles.restoreBtn}
                      onClick={() => setRestoreTarget(card.card_name)}
                    >
                      ↩ Restore
                    </button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      {restoreTarget && (
        <ConfirmDialog
          message={`Restore "${restoreTarget.length > 80 ? restoreTarget.slice(0, 80) + '…' : restoreTarget}" to the Card Ledger?`}
          confirmLabel="Restore"
          onConfirm={handleRestore}
          onCancel={() => setRestoreTarget(null)}
        />
      )}
    </div>
  )
}
