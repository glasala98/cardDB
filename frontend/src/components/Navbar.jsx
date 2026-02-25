import { NavLink } from 'react-router-dom'
import styles from './Navbar.module.css'

const NAV_ITEMS = [
  { to: '/ledger',    label: 'Card Ledger',  icon: '📋' },
  { to: '/portfolio', label: 'Portfolio',    icon: '📈' },
  { to: '/master-db', label: 'Master DB',   icon: '🏒' },
  { to: '/nhl-stats', label: 'NHL Stats',   icon: '🌟' },
]

export default function Navbar() {
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
    </nav>
  )
}
