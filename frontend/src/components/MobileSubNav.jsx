import { NavLink, useLocation } from 'react-router-dom'
import { useAuth } from '../context/AuthContext'
import styles from './MobileSubNav.module.css'

const GROUPS = [
  {
    routes: ['/catalog', '/releases', '/sets', '/trending', '/young-guns'],
    sub: [
      { to: '/catalog',    label: 'Browse'       },
      { to: '/releases',   label: 'New Releases' },
      { to: '/sets',       label: 'Sets'         },
      { to: '/trending',   label: 'Trending'     },
      { to: '/young-guns', label: 'Young Guns',  auth: true },
    ],
  },
  {
    routes: ['/my-cards', '/my-cards/archive', '/my-cards/collection'],
    sub: [
      { to: '/my-cards',            label: 'Tracked'    },
      { to: '/my-cards/collection', label: 'Collection' },
      { to: '/my-cards/archive',    label: 'Archive'    },
    ],
  },
  {
    routes: ['/portfolio', '/charts'],
    sub: [
      { to: '/portfolio', label: 'Overview' },
      { to: '/charts',    label: 'Charts'   },
    ],
  },
]

export default function MobileSubNav() {
  const { pathname } = useLocation()
  const { user } = useAuth()

  const group = GROUPS.find(g =>
    g.sub.some(s => pathname === s.to || pathname.startsWith(s.to + '/'))
  )
  if (!group || group.sub.length <= 1) return null

  const links = group.sub.filter(s => !s.auth || user)
  if (links.length <= 1) return null

  return (
    <div className={styles.strip}>
      {links.map(l => (
        <NavLink
          key={l.to}
          to={l.to}
          end
          className={({ isActive }) => `${styles.pill} ${isActive ? styles.pillActive : ''}`}
        >
          {l.label}
        </NavLink>
      ))}
    </div>
  )
}
