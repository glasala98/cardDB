import { useState } from 'react'
import { NavLink, useNavigate } from 'react-router-dom'
import { useAuth } from '../context/AuthContext'
import { usePublicMode } from '../context/PublicModeContext'
import HelpModal from './HelpModal'
import styles from './Navbar.module.css'

/* ── SVG Icons ───────────────────────────────────────────────── */
const Icons = {
  Logo: () => (
    <svg viewBox="0 0 18 18" fill="none" xmlns="http://www.w3.org/2000/svg">
      <rect x="1" y="3" width="11" height="14" rx="2" fill="currentColor" opacity="0.9"/>
      <rect x="6" y="1" width="11" height="14" rx="2" fill="currentColor" opacity="0.45"/>
    </svg>
  ),
  Ledger: () => (
    <svg viewBox="0 0 18 18" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round">
      <rect x="2" y="2" width="14" height="14" rx="2"/>
      <line x1="6" y1="6" x2="12" y2="6"/>
      <line x1="6" y1="9" x2="12" y2="9"/>
      <line x1="6" y1="12" x2="10" y2="12"/>
    </svg>
  ),
  Portfolio: () => (
    <svg viewBox="0 0 18 18" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round">
      <polyline points="2,13 6,8 9,11 13,5 16,7"/>
      <line x1="2" y1="16" x2="16" y2="16"/>
    </svg>
  ),
  Database: () => (
    <svg viewBox="0 0 18 18" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round">
      <ellipse cx="9" cy="5" rx="7" ry="2.5"/>
      <path d="M2 5v4c0 1.38 3.13 2.5 7 2.5s7-1.12 7-2.5V5"/>
      <path d="M2 9v4c0 1.38 3.13 2.5 7 2.5s7-1.12 7-2.5V9"/>
    </svg>
  ),
  Charts: () => (
    <svg viewBox="0 0 18 18" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round">
      <rect x="2" y="10" width="3" height="6" rx="1"/>
      <rect x="7.5" y="6" width="3" height="10" rx="1"/>
      <rect x="13" y="2" width="3" height="14" rx="1"/>
    </svg>
  ),
  Stats: () => (
    <svg viewBox="0 0 18 18" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round">
      <circle cx="9" cy="6" r="3"/>
      <path d="M3 16c0-3.31 2.69-6 6-6s6 2.69 6 6"/>
    </svg>
  ),
  Archive: () => (
    <svg viewBox="0 0 18 18" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round">
      <rect x="2" y="3" width="14" height="3" rx="1"/>
      <path d="M3 6v9a1 1 0 001 1h10a1 1 0 001-1V6"/>
      <line x1="7" y1="10" x2="11" y2="10"/>
    </svg>
  ),
  Catalog: () => (
    <svg viewBox="0 0 18 18" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round">
      <rect x="2" y="2" width="6" height="6" rx="1"/>
      <rect x="10" y="2" width="6" height="6" rx="1"/>
      <rect x="2" y="10" width="6" height="6" rx="1"/>
      <rect x="10" y="10" width="6" height="6" rx="1"/>
    </svg>
  ),
  Collection: () => (
    <svg viewBox="0 0 18 18" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round">
      <rect x="2" y="4" width="9" height="11" rx="1.5"/>
      <rect x="7" y="2" width="9" height="11" rx="1.5"/>
      <line x1="5" y1="8" x2="9" y2="8"/>
      <line x1="5" y1="11" x2="8" y2="11"/>
    </svg>
  ),
  Admin: () => (
    <svg viewBox="0 0 18 18" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round">
      <circle cx="9" cy="9" r="2.5"/>
      <path d="M9 2v1.5M9 14.5V16M2 9h1.5M14.5 9H16M4.1 4.1l1.1 1.1M12.8 12.8l1.1 1.1M13.9 4.1l-1.1 1.1M5.2 12.8l-1.1 1.1"/>
    </svg>
  ),
  Logout: () => (
    <svg viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" width="14" height="14">
      <path d="M6 2H3a1 1 0 00-1 1v10a1 1 0 001 1h3"/>
      <polyline points="11,5 14,8 11,11"/>
      <line x1="14" y1="8" x2="6" y2="8"/>
    </svg>
  ),
  Share: () => (
    <svg viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" width="14" height="14">
      <circle cx="12" cy="3" r="1.5"/>
      <circle cx="3" cy="8" r="1.5"/>
      <circle cx="12" cy="13" r="1.5"/>
      <line x1="4.4" y1="7.2" x2="10.6" y2="3.8"/>
      <line x1="4.4" y1="8.8" x2="10.6" y2="12.2"/>
    </svg>
  ),
  Help: () => (
    <svg viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" width="14" height="14">
      <circle cx="8" cy="8" r="6.5"/>
      <path d="M6 6.5a2 2 0 113 1.73c-.5.28-1 .8-1 1.77"/>
      <circle cx="8" cy="12" r="0.6" fill="currentColor"/>
    </svg>
  ),
  Check: () => (
    <svg viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" width="14" height="14">
      <polyline points="2,8 6,12 14,4"/>
    </svg>
  ),
}

const CATALOG_ITEMS = [
  { to: '/catalog',    label: 'Card Catalog',  Icon: Icons.Catalog    },
  { to: '/collection', label: 'My Collection', Icon: Icons.Collection },
]

const ACCOUNT_ITEMS = [
  { to: '/ledger',    label: 'Card Ledger', Icon: Icons.Ledger   },
  { to: '/portfolio', label: 'Portfolio',   Icon: Icons.Portfolio },
  { to: '/master-db', label: 'Master DB',   Icon: Icons.Database  },
  { to: '/charts',    label: 'Charts',      Icon: Icons.Charts    },
  { to: '/nhl-stats', label: 'NHL Stats',   Icon: Icons.Stats     },
]

const ADMIN_ITEMS = [
  { to: '/archive', label: 'Archive', Icon: Icons.Archive },
  { to: '/admin',   label: 'Admin',   Icon: Icons.Admin   },
]

function NavGroup({ label, items }) {
  return (
    <div className={styles.navGroup}>
      <span className={styles.groupLabel}>{label}</span>
      <ul className={styles.links}>
        {items.map(({ to, label: itemLabel, Icon }) => (
          <li key={to}>
            <NavLink
              to={to}
              className={({ isActive }) => `${styles.link} ${isActive ? styles.active : ''}`}
            >
              <span className={styles.icon}><Icon /></span>
              <span className={styles.label}>{itemLabel}</span>
            </NavLink>
          </li>
        ))}
      </ul>
    </div>
  )
}

export default function Navbar() {
  const { user, logout } = useAuth()
  const navigate = useNavigate()
  const isPublic = usePublicMode()
  const [showHelp, setShowHelp] = useState(false)

  const handleLogout = async () => {
    await logout()
    navigate('/login', { replace: true })
  }

  const isAdmin = user?.role === 'admin'
  const initials = (user?.display_name || user?.username || '?').slice(0, 2).toUpperCase()

  return (
    <nav className={styles.nav}>
      <div className={styles.logo}>
        <div className={styles.logoMark}>
          <Icons.Logo />
        </div>
        <div className={styles.logoText}>
          <span className={styles.logoName}>CardDB</span>
          <span className={styles.logoSub}>Market Tracker</span>
        </div>
        {isPublic && <span className={styles.publicBadge}>View Only</span>}
      </div>

      <div className={styles.navGroups}>
        <NavGroup label="Catalog" items={CATALOG_ITEMS} />
        <NavGroup label="My Account" items={ACCOUNT_ITEMS} />
        {isAdmin && !isPublic && (
          <NavGroup label="Admin" items={ADMIN_ITEMS} />
        )}
      </div>

      {user && !isPublic && (
        <div className={styles.userArea}>
          <div className={styles.userRow}>
            <div className={styles.userAvatar}>{initials}</div>
            <span className={styles.userName}>{user.display_name || user.username}</span>
          </div>
          <div className={styles.actionRow}>
            <button className={styles.iconBtn} onClick={() => setShowHelp(true)} title="Help">
              <Icons.Help />
            </button>
            <ShareBtn />
            <button className={styles.logoutBtn} onClick={handleLogout} title="Sign out">
              <Icons.Logout />
              Sign out
            </button>
          </div>
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
      className={styles.iconBtn}
      onClick={share}
      title="Copy shareable read-only link"
      style={copied ? { color: 'var(--success)', borderColor: 'rgba(0,201,122,0.4)' } : {}}
    >
      {copied
        ? <svg viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" width="14" height="14"><polyline points="2,8 6,12 14,4"/></svg>
        : <Icons.Share />
      }
    </button>
  )
}
