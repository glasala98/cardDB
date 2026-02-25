import styles from './CardTable.module.css'

/**
 * Generic sortable data table.
 * Props:
 *   columns: [{ key, label, render? }]
 *   rows: array of objects
 *   onRowClick?: (row) => void
 *   sortKey, sortDir, onSort: (key) => void
 */
export default function CardTable({ columns, rows, onRowClick, sortKey, sortDir, onSort }) {
  if (!rows || rows.length === 0) {
    return <p className={styles.empty}>No records to display.</p>
  }

  return (
    <div className={styles.wrapper}>
      <table className={styles.table}>
        <thead>
          <tr>
            {columns.map(col => (
              <th
                key={col.key}
                className={styles.th}
                onClick={() => onSort && onSort(col.key)}
                style={{ cursor: onSort ? 'pointer' : 'default' }}
              >
                {col.label}
                {sortKey === col.key && (
                  <span className={styles.sortArrow}>{sortDir === 'asc' ? ' ↑' : ' ↓'}</span>
                )}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {rows.map((row, i) => (
            <tr
              key={i}
              className={`${styles.tr} ${onRowClick ? styles.clickable : ''}`}
              onClick={() => onRowClick && onRowClick(row)}
            >
              {columns.map(col => (
                <td key={col.key} className={styles.td}>
                  {col.render ? col.render(row[col.key], row) : row[col.key] ?? '—'}
                </td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}
