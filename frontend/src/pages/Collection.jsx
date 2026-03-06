import { useState, useEffect, useCallback } from 'react'
import { getCollection, updateCollectionItem, removeFromCollection } from '../api/collection'
import { useCurrency } from '../context/CurrencyContext'
import PageTabs from '../components/PageTabs'
import styles from './Collection.module.css'
import pageStyles from './Page.module.css'

const CATALOG_TABS = [
  { to: '/catalog',    label: 'Browse'        },
  { to: '/collection', label: 'My Collection' },
]

const SPORTS = ['NHL', 'NBA', 'NFL', 'MLB']

export default function Collection() {
  const { fmtPrice } = useCurrency()
  const [items,    setItems]   = useState([])
  const [summary,  setSummary] = useState({ total_cards: 0, total_value: 0, total_cost: 0 })
  const [loading,  setLoading] = useState(true)
  const [error,    setError]   = useState(null)
  const [search,   setSearch]  = useState('')
  const [sport,    setSport]   = useState('')
  const [editId,   setEditId]  = useState(null)
  const [editData, setEditData] = useState({})

  const load = useCallback(() => {
    setLoading(true)
    getCollection()
      .then(data => {
        setItems(data.items || [])
        setSummary({
          total_cards: data.total_cards || 0,
          total_value: data.total_value || 0,
          total_cost:  data.total_cost  || 0,
        })
      })
      .catch(e => setError(e.message))
      .finally(() => setLoading(false))
  }, [])

  useEffect(() => { load() }, [load])

  const handleRemove = async (id) => {
    if (!confirm('Remove this card from your collection?')) return
    try {
      await removeFromCollection(id)
      setItems(prev => prev.filter(i => i.id !== id))
    } catch (e) {
      alert(e.message)
    }
  }

  const startEdit = (item) => {
    setEditId(item.id)
    setEditData({
      cost_basis:    item.cost_basis ?? '',
      purchase_date: item.purchase_date ?? '',
      quantity:      item.quantity ?? 1,
      notes:         item.notes ?? '',
    })
  }

  const saveEdit = async (id) => {
    try {
      await updateCollectionItem(id, {
        cost_basis:    editData.cost_basis !== '' ? parseFloat(editData.cost_basis) : null,
        purchase_date: editData.purchase_date || null,
        quantity:      parseInt(editData.quantity) || 1,
        notes:         editData.notes,
      })
      setItems(prev => prev.map(i => i.id === id
        ? { ...i, ...editData,
            cost_basis: editData.cost_basis !== '' ? parseFloat(editData.cost_basis) : null,
            quantity: parseInt(editData.quantity) || 1 }
        : i
      ))
      setEditId(null)
    } catch (e) {
      alert(e.message)
    }
  }

  const filtered = items.filter(item => {
    if (sport && item.sport !== sport) return false
    if (search) {
      const s = search.toLowerCase()
      return item.player_name?.toLowerCase().includes(s)
          || item.set_name?.toLowerCase().includes(s)
    }
    return true
  })

  const totalPL = filtered.reduce((sum, item) => {
    const val  = (item.fair_value  || 0) * (item.quantity || 1)
    const cost = (item.cost_basis  != null ? item.cost_basis : 0) * (item.quantity || 1)
    return sum + (val - cost)
  }, 0)

  const totalValue = filtered.reduce((sum, i) => sum + (i.fair_value || 0) * (i.quantity || 1), 0)
  const totalCost  = filtered.reduce((sum, i) => i.cost_basis != null
    ? sum + i.cost_basis * (i.quantity || 1) : sum, 0)

  return (
    <div className={pageStyles.page}>
      <PageTabs tabs={CATALOG_TABS} />
      {/* Header */}
      <div className={pageStyles.header}>
        <h1 className={pageStyles.title}>My Collection</h1>
        <span className={pageStyles.count}>{summary.total_cards.toLocaleString()} cards</span>
        <div style={{ marginLeft: 'auto' }}>
        </div>
      </div>

      {/* Summary stats */}
      <div className={styles.stats}>
        <div className={styles.stat}>
          <span className={styles.statLabel}>Cards (filtered)</span>
          <span className={styles.statValue}>{filtered.length.toLocaleString()}</span>
        </div>
        <div className={styles.stat}>
          <span className={styles.statLabel}>Market Value</span>
          <span className={styles.statValue}>{fmtPrice(totalValue)}</span>
        </div>
        <div className={styles.stat}>
          <span className={styles.statLabel}>Total Cost</span>
          <span className={styles.statValue}>{fmtPrice(totalCost)}</span>
        </div>
        <div className={styles.stat}>
          <span className={styles.statLabel}>Gain / Loss</span>
          <span className={`${styles.statValue} ${totalPL >= 0 ? styles.gain : styles.loss}`}>
            {totalPL >= 0 ? '+' : ''}{fmtPrice(totalPL)}
          </span>
        </div>
      </div>

      {/* Filters */}
      <div className={pageStyles.toolbar}>
        <input
          className={pageStyles.search}
          placeholder="Search player or set..."
          value={search}
          onChange={e => setSearch(e.target.value)}
        />
        <div className={styles.sportTabs}>
          {['', ...SPORTS].map(s => (
            <button
              key={s || 'all'}
              className={`${styles.tab} ${sport === s ? styles.tabActive : ''}`}
              onClick={() => setSport(s)}
            >
              {s || 'All'}
            </button>
          ))}
        </div>
      </div>

      {error  && <div className={pageStyles.error}>{error}</div>}
      {loading && <div className={pageStyles.status}>Loading...</div>}

      {!loading && filtered.length === 0 && (
        <div className={pageStyles.status}>
          {items.length === 0
            ? 'Your collection is empty — browse the Card Catalog and add cards.'
            : 'No cards match your filters.'}
        </div>
      )}

      {!loading && filtered.length > 0 && (
        <div className={styles.tableWrap}>
          <table className={styles.table}>
            <thead>
              <tr>
                <th>Sport</th>
                <th>Year</th>
                <th>Set</th>
                <th>#</th>
                <th>Player</th>
                <th>Grade</th>
                <th>Qty</th>
                <th>Cost</th>
                <th>Market</th>
                <th>P&amp;L</th>
                <th></th>
              </tr>
            </thead>
            <tbody>
              {filtered.map(item => {
                const isEditing = editId === item.id
                const pl = ((item.fair_value || 0) - (item.cost_basis || 0)) * (item.quantity || 1)
                return (
                  <tr key={item.id} className={isEditing ? styles.editRow : ''}>
                    <td><span className={styles.sportBadge}>{item.sport}</span></td>
                    <td>{item.year || '—'}</td>
                    <td className={styles.setCell} title={item.set_name}>
                      {item.set_name?.length > 28 ? item.set_name.slice(0, 26) + '…' : item.set_name || '—'}
                    </td>
                    <td>{item.card_number || '—'}</td>
                    <td className={styles.playerCell}>
                      {item.player_name}
                      {item.is_rookie && <span className={styles.rcBadge}>RC</span>}
                    </td>
                    <td>{item.grade}</td>
                    <td>
                      {isEditing
                        ? <input
                            className={styles.inlineInput}
                            type="number" min="1"
                            value={editData.quantity}
                            onChange={e => setEditData(p => ({ ...p, quantity: e.target.value }))}
                            style={{ width: 48 }}
                          />
                        : item.quantity
                      }
                    </td>
                    <td>
                      {isEditing
                        ? <input
                            className={styles.inlineInput}
                            type="number" step="0.01" placeholder="—"
                            value={editData.cost_basis}
                            onChange={e => setEditData(p => ({ ...p, cost_basis: e.target.value }))}
                            style={{ width: 72 }}
                          />
                        : item.cost_basis != null ? fmtPrice(item.cost_basis) : <span className={styles.muted}>—</span>
                      }
                    </td>
                    <td>
                      {item.fair_value != null
                        ? <span className={styles.price}>{fmtPrice(item.fair_value)}</span>
                        : <span className={styles.muted}>—</span>}
                    </td>
                    <td>
                      {item.cost_basis != null && item.fair_value != null
                        ? <span className={pl >= 0 ? styles.gain : styles.loss}>
                            {pl >= 0 ? '+' : ''}{fmtPrice(pl)}
                          </span>
                        : <span className={styles.muted}>—</span>}
                    </td>
                    <td className={styles.actions}>
                      {isEditing ? (
                        <>
                          <button className={styles.saveBtn} onClick={() => saveEdit(item.id)}>Save</button>
                          <button className={styles.cancelBtn} onClick={() => setEditId(null)}>✕</button>
                        </>
                      ) : (
                        <>
                          <button className={styles.editBtn} onClick={() => startEdit(item)} title="Edit">✎</button>
                          <button className={styles.removeBtn} onClick={() => handleRemove(item.id)} title="Remove">✕</button>
                        </>
                      )}
                    </td>
                  </tr>
                )
              })}
            </tbody>
          </table>
        </div>
      )}
    </div>
  )
}
