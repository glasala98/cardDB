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
  Catalog: () => (
    <svg viewBox="0 0 18 18" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round">
      <rect x="2" y="2" width="6" height="6" rx="1"/>
      <rect x="10" y="2" width="6" height="6" rx="1"/>
      <rect x="2" y="10" width="6" height="6" rx="1"/>
      <rect x="10" y="10" width="6" height="6" rx="1"/>
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
  Settings: () => (
    <svg viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" width="14" height="14">
      <circle cx="8" cy="8" r="2.2"/>
      <path d="M8 2v1M8 13v1M2 8h1M13 8h1M3.8 3.8l.7.7M11.5 11.5l.7.7M12.2 3.8l-.7.7M4.5 11.5l-.7.7"/>
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
}

const NAV_ITEMS = [
  { to: '/catalog',   label: 'Catalog',   Icon: Icons.Catalog,   public: true  },
  { to: '/ledger',    label: 'Ledger',    Icon: Icons.Ledger,    public: false },
  { to: '/portfolio', label: 'Portfolio', Icon: Icons.Portfolio,  public: false },
]

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
        <img src="/logo.png" alt="CardDB" className={styles.logoImg} />
        <div className={styles.logoText}>
          <span className={styles.logoName}>CardDB</span>
          <span className={styles.logoSub}>Market Tracker</span>
        </div>
        {isPublic && <span className={styles.publicBadge}>View Only</span>}
      </div>

      <ul className={styles.links}>
        {NAV_ITEMS.filter(item => user || item.public).map(({ to, label, Icon }) => (
          <li key={to}>
            <NavLink
              to={to}
              className={({ isActive }) => `${styles.link} ${isActive ? styles.active : ''}`}
            >
              <span className={styles.icon}><Icon /></span>
              <span className={styles.label}>{label}</span>
            </NavLink>
          </li>
        ))}
        {/* Settings tab — visible only on mobile via CSS, only when logged in */}
        {user && (
          <li className={styles.mobileSettingsTab}>
            <NavLink
              to="/settings"
              className={({ isActive }) => `${styles.link} ${isActive ? styles.active : ''}`}
            >
              <span className={styles.icon}><Icons.Settings /></span>
              <span className={styles.label}>Settings</span>
            </NavLink>
          </li>
        )}
      </ul>

      {user ? (
        <div className={styles.userArea}>
          <div className={styles.userRow}>
            <div className={styles.userAvatar}>{initials}</div>
            <span className={styles.userName}>{user.display_name || user.username}</span>
          </div>
          {!isPublic && (
            <div className={styles.actionRow}>
              <button className={styles.iconBtn} onClick={() => setShowHelp(true)} title="Help">
                <Icons.Help />
              </button>
              <ShareBtn />
              <button className={styles.iconBtn} onClick={() => navigate('/settings')} title="Settings">
                <Icons.Settings />
              </button>
              <button className={styles.logoutBtn} onClick={handleLogout} title="Sign out">
                <Icons.Logout />
                Sign out
              </button>
            </div>
          )}
        </div>
      ) : (
        <div className={styles.authArea}>
          <button className={styles.signInBtn} onClick={() => navigate('/login')}>Sign in</button>
          <button className={styles.signUpBtn} onClick={() => navigate('/signup')}>Create account</button>
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
