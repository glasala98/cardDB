import { useState, useEffect } from 'react'
import { getUsers, createUser, deleteUser, changePassword } from '../api/admin'
import { useAuth } from '../context/AuthContext'
import pageStyles from './Page.module.css'
import styles from './Admin.module.css'

export default function Admin() {
  const { user: me } = useAuth()
  const [users,   setUsers]   = useState([])
  const [loading, setLoading] = useState(true)
  const [error,   setError]   = useState(null)
  const [toast,   setToast]   = useState(null)

  // Add user form
  const [newUser,   setNewUser]   = useState({ username: '', password: '', display_name: '', role: 'user' })
  const [adding,    setAdding]    = useState(false)

  // Password change
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
    } catch (e) {
      showToast(e.message, 'error')
    } finally {
      setAdding(false)
    }
  }

  const handleDelete = async (username) => {
    if (!confirm(`Delete user "${username}"? This cannot be undone.`)) return
    try {
      await deleteUser(username)
      showToast(`User "${username}" deleted`)
      load()
    } catch (e) {
      showToast(e.message, 'error')
    }
  }

  const handlePasswordChange = async () => {
    if (!newPw || !pwTarget) return
    setSavingPw(true)
    try {
      await changePassword(pwTarget, newPw)
      showToast(`Password updated for "${pwTarget}"`)
      setPwTarget(null); setNewPw('')
    } catch (e) {
      showToast(e.message, 'error')
    } finally {
      setSavingPw(false)
    }
  }

  if (loading) return <p className={pageStyles.status}>Loading…</p>
  if (error)   return <p className={pageStyles.error}>Error: {error}</p>

  return (
    <div className={pageStyles.page}>
      {toast && <div className={`${styles.toast} ${styles[toast.type]}`}>{toast.msg}</div>}

      <div className={pageStyles.header}>
        <h1 className={pageStyles.title}>User Management</h1>
        <span className={pageStyles.count}>{users.length} users</span>
      </div>

      {/* User Table */}
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
                <td className={styles.td}><strong>{u.username}</strong> {u.username === me?.username && <span className={styles.youBadge}>you</span>}</td>
                <td className={styles.td}>{u.display_name}</td>
                <td className={styles.td}>
                  <span className={`${styles.roleBadge} ${u.role === 'admin' ? styles.admin : ''}`}>{u.role}</span>
                </td>
                <td className={`${styles.td} ${styles.actions}`}>
                  <button className={styles.pwBtn} onClick={() => { setPwTarget(u.username); setNewPw('') }}>
                    Change PW
                  </button>
                  {u.username !== me?.username && (
                    <button className={styles.delBtn} onClick={() => handleDelete(u.username)}>
                      Delete
                    </button>
                  )}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      {/* Change Password inline */}
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

      {/* Add User */}
      <div className={styles.addSection}>
        <h2 className={styles.addTitle}>Add New User</h2>
        <div className={styles.addForm}>
          <input
            className={styles.input}
            placeholder="Username"
            value={newUser.username}
            onChange={e => setNewUser(p => ({ ...p, username: e.target.value }))}
          />
          <input
            className={styles.input}
            placeholder="Display Name"
            value={newUser.display_name}
            onChange={e => setNewUser(p => ({ ...p, display_name: e.target.value }))}
          />
          <input
            className={styles.input}
            type="password"
            placeholder="Password"
            value={newUser.password}
            onChange={e => setNewUser(p => ({ ...p, password: e.target.value }))}
          />
          <select
            className={styles.input}
            value={newUser.role}
            onChange={e => setNewUser(p => ({ ...p, role: e.target.value }))}
          >
            <option value="user">user</option>
            <option value="admin">admin</option>
          </select>
          <button
            className={styles.addBtn}
            onClick={handleAdd}
            disabled={!newUser.username || !newUser.password || adding}
          >
            {adding ? 'Creating…' : 'Create User'}
          </button>
        </div>
      </div>
    </div>
  )
}
