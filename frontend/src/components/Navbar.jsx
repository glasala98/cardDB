import { useState } from 'react'
import { NavLink, useNavigate } from 'react-router-dom'
import { useAuth } from '../context/AuthContext'
import HelpModal from './HelpModal'
import styles from './Navbar.module.css'

const NAV_ITEMS = [
  { to: '/ledger',    label: 'Card Ledger',  icon: '📋' },
  { to: '/portfolio', label: 'Portfolio',    icon: '📈' },
  { to: '/master-db', label: 'Master DB',   icon: '🏒' },
  { to: '/charts',    label: 'Charts',      icon: '📊' },
  { to: '/nhl-stats', label: 'NHL Stats',   icon: '🌟' },
  { to: '/archive',   label: 'Archive',     icon: '🗃️' },
]

export default function Navbar() {
  const { user, logout } = useAuth()
  const navigate = useNavigate()
  const [showHelp, setShowHelp] = useState(false)

  const handleLogout = async () => {
    await logout()
    navigate('/login', { replace: true })
  }

  const isAdmin = user?.role === 'admin'

  return (
    <nav className={styles.nav}>
      <div className={styles.logo}>
        <span className={styles.logoIcon}>🃏</span>
        <span className={styles.logoText}>Card DB</span>
      </div>

      <ul className={styles.links}>
        {NAV_ITEMS.map(({ to, label, icon }) => (
          <li key={to}>
            <NavLink
              to={to}
              className={({ isActive }) =>
                `${styles.link} ${isActive ? styles.active : ''}`
              }
            >
              <span className={styles.icon}>{icon}</span>
              <span className={styles.label}>{label}</span>
            </NavLink>
          </li>
        ))}
        {isAdmin && (
          <li>
            <NavLink
              to="/admin"
              className={({ isActive }) => `${styles.link} ${isActive ? styles.active : ''}`}
            >
              <span className={styles.icon}>⚙️</span>
              <span className={styles.label}>Admin</span>
            </NavLink>
          </li>
        )}
      </ul>

      {user && (
        <div className={styles.userArea}>
          <button className={styles.helpBtn} onClick={() => setShowHelp(true)} title="Site guide">?</button>
          <ShareBtn />
          <span className={styles.userName}>{user.display_name || user.username}</span>
          <button className={styles.logoutBtn} onClick={handleLogout} title="Sign out">
            ↩ Sign out
          </button>
        </div>
      )}

      {showHelp && <HelpModal onClose={() => setShowHelp(false)} />}
    </nav>
  )
}

function ShareBtn() {
  const [copied, setCopied] = useState(false)
  const share = () => {
    const url = window.location.origin + window.location.pathname + '?public=true'
    navigator.clipboard.writeText(url).then(() => {
      setCopied(true)
      setTimeout(() => setCopied(false), 2000)
    })
  }
  return (
    <button
      className={`${styles.helpBtn} ${styles.shareBtn}`}
      onClick={share}
      title="Copy shareable link (read-only)"
      style={{ width: 'auto', borderRadius: 8, padding: '0 8px', fontSize: 11, fontWeight: 700 }}
    >
      {copied ? '✓' : '🔗'}
    </button>
  )
}
