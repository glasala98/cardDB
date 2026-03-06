import { useState, useEffect } from 'react'
import { useAuth } from '../context/AuthContext'
import { usePreferences } from '../context/PreferencesContext'
import { useCurrency } from '../context/CurrencyContext'
import { getUsers, createUser, deleteUser, changePassword } from '../api/admin'
import pageStyles from './Page.module.css'
import styles from './Settings.module.css'

/* ── Appearance section ─────────────────────────────────────── */
function AppearanceSection() {
  const { density, setDensity } = usePreferences()
  const { currency, toggle } = useCurrency()

  return (
    <section className={styles.section}>
      <h2 className={styles.sectionTitle}>Appearance</h2>

      <div className={styles.settingRow}>
        <div className={styles.settingInfo}>
          <span className={styles.settingLabel}>Currency</span>
          <span className={styles.settingDesc}>Display prices in Canadian or US dollars. Applied across all pages.</span>
        </div>
        <div className={styles.btnGroup}>
          <button
            className={`${styles.densityBtn} ${currency === 'CAD' ? styles.active : ''}`}
            onClick={() => currency !== 'CAD' && toggle()}
          >
            CAD
          </button>
          <button
            className={`${styles.densityBtn} ${currency === 'USD' ? styles.active : ''}`}
            onClick={() => currency !== 'USD' && toggle()}
          >
            USD
          </button>
        </div>
      </div>

      <div className={styles.settingRow} style={{ marginTop: 16 }}>
        <div className={styles.settingInfo}>
          <span className={styles.settingLabel}>Display density</span>
          <span className={styles.settingDesc}>Compact mode fits more rows on screen — great for tablets and smaller displays.</span>
        </div>
        <div className={styles.btnGroup}>
          <button
            className={`${styles.densityBtn} ${density === 'comfortable' ? styles.active : ''}`}
            onClick={() => setDensity('comfortable')}
          >
            Comfortable
          </button>
          <button
            className={`${styles.densityBtn} ${density === 'compact' ? styles.active : ''}`}
            onClick={() => setDensity('compact')}
          >
            Compact
          </button>
        </div>
      </div>
    </section>
  )
}

/* ── User management section (admin only) ───────────────────── */
function UserManagementSection({ me }) {
  const [users,   setUsers]   = useState([])
  const [loading, setLoading] = useState(true)
  const [error,   setError]   = useState(null)
  const [toast,   setToast]   = useState(null)
  const [newUser,   setNewUser]   = useState({ username: '', password: '', display_name: '', role: 'user' })
  const [adding,    setAdding]    = useState(false)
  const [pwTarget,  setPwTarget]  = useState(null)
  const [newPw,     setNewPw]     = useState('')
  const [savingPw,  setSavingPw]  = useState(false)

  const load = () => {
    setLoading(true)
    getUsers()
      .then(d => setUsers(d.users || []))
      .catch(e => setError(e.message))
      .finally(() => setLoading(false))
  }
  useEffect(load, [])

  const showToast = (msg, type = 'success') => {
    setToast({ msg, type })
    setTimeout(() => setToast(null), 3500)
  }

  const handleAdd = async () => {
    if (!newUser.username || !newUser.password) return
    setAdding(true)
    try {
      await createUser(newUser)
      showToast(`User "${newUser.username}" created`)
      setNewUser({ username: '', password: '', display_name: '', role: 'user' })
      load()
    } catch (e) { showToast(e.message, 'error') }
    finally { setAdding(false) }
  }

  const handleDelete = async (username) => {
    if (!confirm(`Delete user "${username}"? This cannot be undone.`)) return
    try {
      await deleteUser(username)
      showToast(`User "${username}" deleted`)
      load()
    } catch (e) { showToast(e.message, 'error') }
  }

  const handlePasswordChange = async () => {
    if (!newPw || !pwTarget) return
    setSavingPw(true)
    try {
      await changePassword(pwTarget, newPw)
      showToast(`Password updated for "${pwTarget}"`)
      setPwTarget(null); setNewPw('')
    } catch (e) { showToast(e.message, 'error') }
    finally { setSavingPw(false) }
  }

  return (
    <section className={styles.section}>
      <h2 className={styles.sectionTitle}>User Management</h2>
      {toast && <div className={`${styles.toast} ${styles[toast.type]}`}>{toast.msg}</div>}
      {loading && <p className={pageStyles.status}>Loading…</p>}
      {error   && <p className={pageStyles.error}>{error}</p>}

      {!loading && (
        <div className={styles.tableWrap}>
          <table className={styles.table}>
            <thead>
              <tr>
                <th className={styles.th}>Username</th>
                <th className={styles.th}>Display Name</th>
                <th className={styles.th}>Role</th>
                <th className={styles.th}>Actions</th>
              </tr>
            </thead>
            <tbody>
              {users.map(u => (
                <tr key={u.username} className={styles.tr}>
                  <td className={styles.td}>
                    <strong>{u.username}</strong>{' '}
                    {u.username === me?.username && <span className={styles.youBadge}>you</span>}
                  </td>
                  <td className={styles.td}>{u.display_name}</td>
                  <td className={styles.td}>
                    <span className={`${styles.roleBadge} ${u.role === 'admin' ? styles.admin : ''}`}>{u.role}</span>
                  </td>
                  <td className={`${styles.td} ${styles.actions}`}>
                    <button className={styles.pwBtn} onClick={() => { setPwTarget(u.username); setNewPw('') }}>
                      Change PW
                    </button>
                    {u.username !== me?.username && (
                      <button className={styles.delBtn} onClick={() => handleDelete(u.username)}>Delete</button>
                    )}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      {pwTarget && (
        <div className={styles.pwBox}>
          <strong>Change password for {pwTarget}</strong>
          <div className={styles.pwRow}>
            <input
              type="password"
              placeholder="New password"
              value={newPw}
              onChange={e => setNewPw(e.target.value)}
              className={styles.input}
              onKeyDown={e => e.key === 'Enter' && handlePasswordChange()}
            />
            <button className={styles.saveBtn} onClick={handlePasswordChange} disabled={!newPw || savingPw}>
              {savingPw ? 'Saving…' : 'Save'}
            </button>
            <button className={styles.cancelBtn} onClick={() => setPwTarget(null)}>Cancel</button>
          </div>
        </div>
      )}

      <div className={styles.addSection}>
        <h3 className={styles.addTitle}>Add New User</h3>
        <div className={styles.addForm}>
          <input className={styles.input} placeholder="Username" value={newUser.username}
            onChange={e => setNewUser(p => ({ ...p, username: e.target.value }))} />
          <input className={styles.input} placeholder="Display Name" value={newUser.display_name}
            onChange={e => setNewUser(p => ({ ...p, display_name: e.target.value }))} />
          <input className={styles.input} type="password" placeholder="Password" value={newUser.password}
            onChange={e => setNewUser(p => ({ ...p, password: e.target.value }))} />
          <select className={styles.input} value={newUser.role}
            onChange={e => setNewUser(p => ({ ...p, role: e.target.value }))}>
            <option value="user">user</option>
            <option value="guest">guest</option>
            <option value="admin">admin</option>
          </select>
          <button className={styles.addBtn} onClick={handleAdd}
            disabled={!newUser.username || !newUser.password || adding}>
            {adding ? 'Creating…' : 'Create User'}
          </button>
        </div>
      </div>
    </section>
  )
}

/* ── Page ───────────────────────────────────────────────────── */
export default function Settings() {
  const { user } = useAuth()
  const isAdmin = user?.role === 'admin'

  return (
    <div className={pageStyles.page}>
      <div className={pageStyles.header}>
        <h1 className={pageStyles.title}>Settings</h1>
      </div>

      <AppearanceSection />
      {isAdmin && <UserManagementSection me={user} />}
    </div>
  )
}
