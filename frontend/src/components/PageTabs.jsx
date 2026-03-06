import { NavLink } from 'react-router-dom'
import styles from './PageTabs.module.css'

export default function PageTabs({ tabs }) {
  return (
    <nav className={styles.tabs}>
      {tabs.map(({ to, label }) => (
        <NavLink
          key={to}
          to={to}
          end
          className={({ isActive }) => `${styles.tab} ${isActive ? styles.active : ''}`}
        >
          {label}
        </NavLink>
      ))}
    </nav>
  )
}
