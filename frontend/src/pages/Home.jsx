import { useState, useEffect } from 'react'
import { useNavigate, Link } from 'react-router-dom'
import { getCatalogStats, aiSearchCatalog } from '../api/catalog'
import styles from './Home.module.css'

const NAV = [
  { to: '/catalog',  label: 'Browse'   },
  { to: '/trending', label: 'Trending' },
  { to: '/sets',     label: 'Sets'     },
  { to: '/releases', label: 'Releases' },
]

const SPORTS = ['NHL', 'NBA', 'NFL', 'MLB']

function fmt(n) {
  if (!n) return '—'
  if (n >= 1_000_000) return (n / 1_000_000).toFixed(1) + 'M'
  if (n >= 1_000)     return Math.round(n / 1_000) + 'K'
  return n.toLocaleString()
}

export default function Home() {
  const [query,   setQuery]   = useState('')
  const [loading, setLoading] = useState(false)
  const [stats,   setStats]   = useState(null)
  const navigate = useNavigate()

  useEffect(() => {
    document.title = 'CardDB — Sports Card Price Database'
    getCatalogStats().then(setStats).catch(() => {})
  }, [])

  function handleSearch(e) {
    e.preventDefault()
    const q = query.trim()
    if (!q) { navigate('/catalog'); return }
    setLoading(true)
    aiSearchCatalog(q)
      .then(data => {
        // Pass AI results to catalog via sessionStorage so catalog can display them
        sessionStorage.setItem('aiHomeResult', JSON.stringify({ query: q, ...data }))
        navigate('/catalog?ai=1')
      })
      .catch(() => {
        // Fallback to regular search if AI fails
        navigate(`/catalog?search=${encodeURIComponent(q)}`)
      })
      .finally(() => setLoading(false))
  }

  return (
    <div className={styles.page}>

      {/* Top nav */}
      <nav className={styles.topNav}>
        <Link to="/" className={styles.navBrand}>
          <img src="/logo.png" alt="CardDB" className={styles.navLogo} />
          CardDB
        </Link>
        {NAV.map(n => (
          <Link key={n.to} to={n.to} className={styles.navLink}>{n.label}</Link>
        ))}
        <div className={styles.navSpacer} />
        <Link to="/login"  className={styles.navSignIn}>Sign in</Link>
        <Link to="/signup" className={styles.navCta}>Create account</Link>
      </nav>

      {/* Hero */}
      <div className={styles.hero}>

        <img src="/logo.png" alt="CardDB" className={styles.emblem} />
        <div className={styles.eyebrow}>Free · No account required</div>
        <h1 className={styles.title}>Sports Card Prices</h1>
        <p className={styles.sub}>
          Real eBay sold data for NHL, NBA, NFL &amp; MLB.<br />
          Search any player, set, or year.
        </p>

        {/* AI search bar */}
        <form className={styles.searchWrap} onSubmit={handleSearch}>
          <div className={styles.aiBar}>
            <span className={styles.aiIcon}>✦</span>
            <input
              className={styles.aiInput}
              type="text"
              placeholder='Ask AI — e.g. "Connor McDavid Young Guns under $200"'
              value={query}
              onChange={e => setQuery(e.target.value)}
              autoFocus
            />
            <button className={styles.aiBtn} type="submit" disabled={loading}>
              {loading ? '…' : 'Search'}
            </button>
          </div>
        </form>

        <div className={styles.sportRow}>
          {SPORTS.map(s => (
            <button key={s} className={styles.sportBtn}
              onClick={() => navigate(`/catalog?sport=${s}`)}>
              {s}
            </button>
          ))}
        </div>

        {stats && (
          <div className={styles.statsRow}>
            <div className={styles.stat}>
              <span className={styles.statNum}>{fmt(stats.card_count)}</span>
              <span className={styles.statLabel}>Cards tracked</span>
            </div>
            <div className={styles.statDivider} />
            <div className={styles.stat}>
              <span className={styles.statNum}>{fmt(stats.priced_count)}</span>
              <span className={styles.statLabel}>Prices available</span>
            </div>
            <div className={styles.statDivider} />
            <div className={styles.stat}>
              <span className={styles.statNum}>{fmt(stats.total_sales)}</span>
              <span className={styles.statLabel}>eBay sales indexed</span>
            </div>
          </div>
        )}
      </div>
    </div>
  )
}
