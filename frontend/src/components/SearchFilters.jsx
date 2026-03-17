import styles from './SearchFilters.module.css'

const SOURCES = ['ebay', 'goldin', 'heritage', 'pwcc', 'fanatics', 'pristine', 'myslabs']
const SORTS = [
  { value: 'date_desc',  label: 'Newest' },
  { value: 'date_asc',   label: 'Oldest' },
  { value: 'price_desc', label: 'Price ↓' },
  { value: 'price_asc',  label: 'Price ↑' },
]

export default function SearchFilters({ filters, onChange, totalCount }) {
  function set(key, val) { onChange({ ...filters, [key]: val }) }
  function toggleSource(src) {
    const cur = filters.sources ?? []
    const next = cur.includes(src) ? cur.filter(s => s !== src) : [...cur, src]
    set('sources', next)
  }

  return (
    <div className={styles.wrap}>
      <div className={styles.row}>
        <div className={styles.sources}>
          {SOURCES.map(src => (
            <button
              key={src}
              className={`${styles.srcBtn} ${(filters.sources ?? []).includes(src) ? styles.active : ''}`}
              onClick={() => toggleSource(src)}
            >
              {src}
            </button>
          ))}
        </div>
        <div className={styles.right}>
          <select
            className={styles.select}
            value={filters.sort ?? 'date_desc'}
            onChange={e => set('sort', e.target.value)}
          >
            {SORTS.map(s => <option key={s.value} value={s.value}>{s.label}</option>)}
          </select>
          {totalCount != null && (
            <span className={styles.count}>{totalCount.toLocaleString()} sales</span>
          )}
        </div>
      </div>
      <div className={styles.row}>
        <label className={styles.label}>Price</label>
        <input
          className={styles.numInput}
          type="number"
          placeholder="Min $"
          value={filters.price_min ?? ''}
          onChange={e => set('price_min', e.target.value || undefined)}
          min={0}
        />
        <span className={styles.dash}>–</span>
        <input
          className={styles.numInput}
          type="number"
          placeholder="Max $"
          value={filters.price_max ?? ''}
          onChange={e => set('price_max', e.target.value || undefined)}
          min={0}
        />
        <label className={styles.label} style={{ marginLeft: 16 }}>From</label>
        <input
          className={styles.dateInput}
          type="date"
          value={filters.date_from ?? ''}
          onChange={e => set('date_from', e.target.value || undefined)}
        />
        <span className={styles.dash}>–</span>
        <input
          className={styles.dateInput}
          type="date"
          value={filters.date_to ?? ''}
          onChange={e => set('date_to', e.target.value || undefined)}
        />
        <label className={styles.label} style={{ marginLeft: 16 }}>Grade only</label>
        <input
          type="checkbox"
          checked={filters.graded_only ?? false}
          onChange={e => set('graded_only', e.target.checked || undefined)}
          className={styles.check}
        />
      </div>
    </div>
  )
}
