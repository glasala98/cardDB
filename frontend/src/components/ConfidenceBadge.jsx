import styles from './ConfidenceBadge.module.css'

const MAP = {
  high:      { label: '✅ High',      cls: 'high',      tip: 'Direct match — exact parallel and serial found' },
  medium:    { label: '🟡 Medium',    cls: 'medium',    tip: 'Set match — parallel name dropped, serial exact' },
  low:       { label: '🟠 Low',       cls: 'low',       tip: 'Broad match — only player, card#, serial used' },
  estimated: { label: '🔴 Estimated', cls: 'estimated', tip: 'No direct sales — price extrapolated from nearby serial comps' },
  none:        { label: '⬜ No data',    cls: 'none',      tip: 'No sales found at any stage' },
  'not found': { label: '⚫ Not Found', cls: 'notfound',  tip: 'Card not found on eBay' },
  unknown:     { label: '⬜ Unknown',   cls: 'none',      tip: 'Not yet scraped' },
}

export default function ConfidenceBadge({ confidence }) {
  const key = (confidence || 'unknown').toLowerCase()
  const { label, cls, tip } = MAP[key] || MAP.unknown
  return (
    <span className={`${styles.badge} ${styles[cls]}`} title={tip}>
      {label}
    </span>
  )
}
