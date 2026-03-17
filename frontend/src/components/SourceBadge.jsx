import styles from './SourceBadge.module.css'

const SOURCE_CONFIG = {
  ebay:     { label: 'eBay',     bg: '#e53238', text: '#fff' },
  goldin:   { label: 'Goldin',   bg: '#1a1a2e', text: '#c9a94b' },
  heritage: { label: 'Heritage', bg: '#003087', text: '#fff' },
  pwcc:     { label: 'PWCC',     bg: '#2d4a22', text: '#7bc67e' },
  fanatics: { label: 'Fanatics', bg: '#cf0a2c', text: '#fff' },
  pristine: { label: 'Pristine', bg: '#1b4f72', text: '#aed6f1' },
  myslabs:  { label: 'MySlabs',  bg: '#4a235a', text: '#d7bde2' },
}

export default function SourceBadge({ source, size = 'sm' }) {
  const cfg = SOURCE_CONFIG[source?.toLowerCase()] ?? {
    label: source ?? '?',
    bg: '#555',
    text: '#fff',
  }
  return (
    <span
      className={`${styles.badge} ${styles[size]}`}
      style={{ backgroundColor: cfg.bg, color: cfg.text }}
    >
      {cfg.label}
    </span>
  )
}
