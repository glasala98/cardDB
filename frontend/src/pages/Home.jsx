import { useState, useEffect } from 'react'
import { useNavigate, Link } from 'react-router-dom'
import { getCatalogStats } from '../api/catalog'
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
  const [query, setQuery] = useState('')
  const [stats, setStats] = useState(null)
  const navigate = useNavigate()

  useEffect(() => {
    document.title = 'CardDB — Sports Card Price Database'
    getCatalogStats().then(setStats).catch(() => {})
  }, [])

  function search(e) {
    e.preventDefault()
    const q = query.trim()
    if (q) navigate(`/catalog?search=${encodeURIComponent(q)}`)
    else   navigate('/catalog')
  }

  return (
    <div className={styles.page}>

      {/* Top nav bar */}
      <nav className={styles.topNav}>
        {NAV.map(n => (
          <Link key={n.to} to={n.to} className={styles.navLink}>{n.label}</Link>
        ))}
        <div className={styles.navSpacer} />
        <Link to="/login"  className={styles.navLink}>Sign in</Link>
        <Link to="/signup" className={styles.navCta}>Create account</Link>
      </nav>

      {/* Hero */}
      <div className={styles.hero}>
        <h1 className={styles.title}>Sports Card Prices</h1>
        {stats && (
          <p className={styles.sub}>
            {fmt(stats.priced_count)} cards priced · {fmt(stats.total_sales)} eBay sales indexed
          </p>
        )}

        <form className={styles.searchBar} onSubmit={search}>
          <input
            className={styles.input}
            type="text"
            placeholder='Search any player, set, or year…'
            value={query}
            onChange={e => setQuery(e.target.value)}
            autoFocus
          />
          <button className={styles.searchBtn} type="submit">Search</button>
        </form>

        <div className={styles.sportRow}>
          {SPORTS.map(s => (
            <button key={s} className={styles.sportBtn}
              onClick={() => navigate(`/catalog?sport=${s}`)}>
              {s}
            </button>
          ))}
        </div>
      </div>

    </div>
  )
}
