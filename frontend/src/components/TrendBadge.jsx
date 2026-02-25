import styles from './TrendBadge.module.css'

const MAP = {
  up:     { label: 'Trending Up',   cls: 'up' },
  down:   { label: 'Trending Down', cls: 'down' },
  stable: { label: 'Stable',        cls: 'stable' },
}

export default function TrendBadge({ trend }) {
  const key = (trend || '').toLowerCase().trim()
  const { label, cls } = MAP[key] || { label: 'No Data', cls: 'nodata' }
  return <span className={`${styles.badge} ${styles[cls]}`}>{label}</span>
}
