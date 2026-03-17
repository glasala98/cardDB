import SourceBadge from './SourceBadge'
import GradeBadge from './GradeBadge'
import styles from './SearchResultRow.module.css'

function fmt(val) {
  if (val == null) return '—'
  return '$' + Number(val).toLocaleString('en-US', { minimumFractionDigits: 0, maximumFractionDigits: 0 })
}

function fmtDate(d) {
  if (!d) return ''
  return new Date(d).toLocaleDateString('en-US', { month: 'short', day: 'numeric', year: 'numeric' })
}

export default function SearchResultRow({ sale, onClick }) {
  const hasPremium = sale.hammer_price != null && sale.buyer_premium_pct != null
  const premium = hasPremium
    ? (sale.price_val - sale.hammer_price).toFixed(0)
    : null

  return (
    <div
      className={styles.row}
      onClick={onClick}
      style={onClick ? { cursor: 'pointer' } : undefined}
    >
      {sale.image_url && (
        <img src={sale.image_url} alt="" className={styles.thumb} loading="lazy" />
      )}
      <div className={styles.main}>
        <div className={styles.titleLine}>
          <span className={styles.title}>{sale.title}</span>
          {sale.serial_number && sale.print_run && (
            <span className={styles.serial}>#{sale.serial_number}/{sale.print_run}</span>
          )}
        </div>
        <div className={styles.meta}>
          <SourceBadge source={sale.source} size="sm" />
          {sale.grade && <GradeBadge grade={sale.grade} />}
          <span className={styles.date}>{fmtDate(sale.sold_date)}</span>
        </div>
      </div>
      <div className={styles.priceBlock}>
        <span className={styles.price}>{fmt(sale.price_val)}</span>
        {hasPremium && (
          <span className={styles.hammer} title={`Hammer: ${fmt(sale.hammer_price)} + ${sale.buyer_premium_pct}% premium`}>
            hammer {fmt(sale.hammer_price)}
          </span>
        )}
      </div>
    </a>
  )
}
