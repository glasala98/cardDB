import { NavLink, useNavigate } from 'react-router-dom'
import { useAuth } from '../context/AuthContext'
import { useCurrency } from '../context/CurrencyContext'
import styles from './Navbar.module.css'

const NAV_ITEMS = [
  { to: '/ledger',    label: 'Card Ledger',  icon: '📋' },
  { to: '/portfolio', label: 'Portfolio',    icon: '📈' },
  { to: '/master-db', label: 'Master DB',   icon: '🏒' },
  { to: '/nhl-stats', label: 'NHL Stats',   icon: '🌟' },
]

export default function Navbar() {
  const { user, logout } = useAuth()
  const { currency, toggle: toggleCurrency } = useCurrency()
  const navigate = useNavigate()

  const handleLogout = async () => {
    await logout()
    navigate('/login', { replace: true })
  }

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
      </ul>

      <div className={styles.currencyToggle}>
        <button
          className={`${styles.currencyBtn} ${currency === 'CAD' ? styles.currencyActive : ''}`}
          onClick={() => currency !== 'CAD' && toggleCurrency()}
        >CAD</button>
        <button
          className={`${styles.currencyBtn} ${currency === 'USD' ? styles.currencyActive : ''}`}
          onClick={() => currency !== 'USD' && toggleCurrency()}
        >USD</button>
      </div>

      {user && (
        <div className={styles.userArea}>
          <span className={styles.userName}>{user.display_name || user.username}</span>
          <button className={styles.logoutBtn} onClick={handleLogout} title="Sign out">
            ↩ Sign out
          </button>
        </div>
      )}
    </nav>
  )
}
