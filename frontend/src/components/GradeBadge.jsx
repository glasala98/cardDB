import styles from './GradeBadge.module.css'

const GRADE_CONFIG = {
  'PSA 10': { bg: '#c8102e', text: '#fff' },
  'PSA 9.5':{ bg: '#e8442a', text: '#fff' },
  'PSA 9':  { bg: '#e86a2a', text: '#fff' },
  'BGS 10': { bg: '#003087', text: '#fff' },
  'BGS 9.5':{ bg: '#1a4fa8', text: '#fff' },
  'BGS 9':  { bg: '#3366cc', text: '#fff' },
  'SGC 10': { bg: '#1a5c1a', text: '#fff' },
  'SGC 9.5':{ bg: '#237a23', text: '#fff' },
  'CGC 10': { bg: '#5c3d8f', text: '#fff' },
}

export default function GradeBadge({ grade }) {
  if (!grade) return null
  const cfg = GRADE_CONFIG[grade] ?? { bg: '#555', text: '#fff' }
  return (
    <span className={styles.badge} style={{ backgroundColor: cfg.bg, color: cfg.text }}>
      {grade}
    </span>
  )
}
