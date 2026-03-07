import { useState, useEffect, useCallback } from 'react'
import {
  getUsers, createUser, deleteUser, changePassword, changeRole,
  getPipelineHealth, getWorkflowStatus, getOutliers, toggleIgnore,
} from '../api/admin'
import { useAuth } from '../context/AuthContext'
import pageStyles from './Page.module.css'
import styles from './Admin.module.css'

const TABS = ['Users', 'Pipeline', 'Outliers']

export default function Admin() {
  const [tab, setTab] = useState('Users')

  return (
    <div className={pageStyles.page}>
      <div className={pageStyles.header}>
        <h1 className={pageStyles.title}>Admin</h1>
      </div>

      <div className={styles.tabRow}>
        {TABS.map(t => (
          <button
            key={t}
            className={`${styles.tabBtn} ${tab === t ? styles.tabBtnActive : ''}`}
            onClick={() => setTab(t)}
          >
            {t}
          </button>
        ))}
      </div>

      {tab === 'Users'    && <UsersTab />}
      {tab === 'Pipeline' && <PipelineTab />}
      {tab === 'Outliers' && <OutliersTab />}
    </div>
  )
}

/* ── Users tab ─────────────────────────────────────────────────────────────── */
function UsersTab() {
  const { user: me } = useAuth()
  const [users,    setUsers]    = useState([])
  const [loading,  setLoading]  = useState(true)
  const [error,    setError]    = useState(null)
  const [toast,    setToast]    = useState(null)
  const [newUser,  setNewUser]  = useState({ username: '', password: '', display_name: '', role: 'user' })
  const [adding,   setAdding]   = useState(false)
  const [pwTarget, setPwTarget] = useState(null)
  const [newPw,    setNewPw]    = useState('')
  const [savingPw, setSavingPw] = useState(false)

  const showToast = (msg, type = 'success') => {
    setToast({ msg, type })
    setTimeout(() => setToast(null), 3500)
  }

  const load = useCallback(() => {
    setLoading(true)
    getUsers()
      .then(d => setUsers(d.users || []))
      .catch(e => setError(e.message))
      .finally(() => setLoading(false))
  }, [])
  useEffect(load, [load])

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
    if (!confirm(`Delete "${username}"? Cannot be undone.`)) return
    try {
      await deleteUser(username)
      showToast(`User "${username}" deleted`)
      load()
    } catch (e) { showToast(e.message, 'error') }
  }

  const handlePw = async () => {
    if (!newPw || !pwTarget) return
    setSavingPw(true)
    try {
      await changePassword(pwTarget, newPw)
      showToast(`Password updated for "${pwTarget}"`)
      setPwTarget(null); setNewPw('')
    } catch (e) { showToast(e.message, 'error') }
    finally { setSavingPw(false) }
  }

  const handleRole = async (username, role) => {
    try {
      await changeRole(username, role)
      showToast(`Role updated for "${username}"`)
      load()
    } catch (e) { showToast(e.message, 'error') }
  }

  if (loading) return <p className={pageStyles.status}>Loading…</p>
  if (error)   return <p className={pageStyles.error}>Error: {error}</p>

  return (
    <>
      {toast && <div className={`${styles.toast} ${styles[toast.type]}`}>{toast.msg}</div>}

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
                  <strong>{u.username}</strong>
                  {u.username === me?.username && <span className={styles.youBadge}>you</span>}
                </td>
                <td className={styles.td}>{u.display_name}</td>
                <td className={styles.td}>
                  {u.username === me?.username ? (
                    <span className={`${styles.roleBadge} ${u.role === 'admin' ? styles.admin : ''}`}>{u.role}</span>
                  ) : (
                    <select
                      className={styles.roleSelect}
                      value={u.role}
                      onChange={e => handleRole(u.username, e.target.value)}
                    >
                      <option value="user">user</option>
                      <option value="admin">admin</option>
                      <option value="guest">guest</option>
                    </select>
                  )}
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

      {pwTarget && (
        <div className={styles.pwBox}>
          <strong>Change password for {pwTarget}</strong>
          <div className={styles.pwRow}>
            <input type="password" placeholder="New password" value={newPw}
              onChange={e => setNewPw(e.target.value)} className={styles.input}
              onKeyDown={e => e.key === 'Enter' && handlePw()} />
            <button className={styles.saveBtn} onClick={handlePw} disabled={!newPw || savingPw}>
              {savingPw ? 'Saving…' : 'Save'}
            </button>
            <button className={styles.cancelBtn} onClick={() => setPwTarget(null)}>Cancel</button>
          </div>
        </div>
      )}

      <div className={styles.addSection}>
        <h2 className={styles.addTitle}>Add New User</h2>
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
            <option value="admin">admin</option>
            <option value="guest">guest</option>
          </select>
          <button className={styles.addBtn}
            onClick={handleAdd} disabled={!newUser.username || !newUser.password || adding}>
            {adding ? 'Creating…' : 'Create User'}
          </button>
        </div>
      </div>
    </>
  )
}

/* ── Pipeline tab ──────────────────────────────────────────────────────────── */
function PipelineTab() {
  const [health,    setHealth]    = useState(null)
  const [workflows, setWorkflows] = useState([])
  const [loading,   setLoading]   = useState(true)
  const [error,     setError]     = useState(null)

  useEffect(() => {
    setLoading(true)
    Promise.all([getPipelineHealth(), getWorkflowStatus()])
      .then(([h, w]) => { setHealth(h); setWorkflows(w.workflows || []) })
      .catch(e => setError(e.message))
      .finally(() => setLoading(false))
  }, [])

  if (loading) return <p className={pageStyles.status}>Loading pipeline data…</p>
  if (error)   return <p className={pageStyles.error}>Error: {error}</p>
  if (!health) return null

  return (
    <div className={styles.pipelineWrap}>
      <div className={styles.statCards}>
        <StatCard label="Catalog Size"   value={health.total_cards.toLocaleString()} />
        <StatCard label="Priced Cards"   value={health.priced_cards.toLocaleString()} />
        <StatCard label="Coverage"       value={`${health.coverage_pct}%`} accent={health.coverage_pct > 50} />
        <StatCard label="Ignored Prices" value={health.ignored_count.toLocaleString()} warn={health.ignored_count > 0} />
        <StatCard label="Outlier Flags"  value={health.outlier_count.toLocaleString()} warn={health.outlier_count > 0} />
      </div>

      <h3 className={styles.sectionTitle}>Coverage by Tier</h3>
      <div className={styles.tableWrap}>
        <table className={styles.table}>
          <thead>
            <tr>
              <th className={styles.th}>Tier</th>
              <th className={styles.th}>Total</th>
              <th className={styles.th}>Priced</th>
              <th className={styles.th}>Coverage</th>
            </tr>
          </thead>
          <tbody>
            {health.tiers.map(t => {
              const pct = t.total > 0 ? Math.round(t.priced / t.total * 100) : 0
              return (
                <tr key={t.tier} className={styles.tr}>
                  <td className={styles.td}>
                    <span className={`${styles.tierBadge} ${styles['tier_' + t.tier]}`}>{t.tier}</span>
                  </td>
                  <td className={styles.td}>{t.total.toLocaleString()}</td>
                  <td className={styles.td}>{t.priced.toLocaleString()}</td>
                  <td className={styles.td}>
                    <div className={styles.barWrap}>
                      <div className={styles.barFill} style={{ width: `${pct}%` }} />
                      <span className={styles.barLabel}>{pct}%</span>
                    </div>
                  </td>
                </tr>
              )
            })}
          </tbody>
        </table>
      </div>

      <h3 className={styles.sectionTitle}>Last Scrape by Sport</h3>
      <div className={styles.sportGrid}>
        {Object.entries(health.last_scraped).map(([sport, ts]) => (
          <div key={sport} className={styles.sportCard}>
            <span className={styles.sportLabel}>{sport}</span>
            <span className={styles.sportTs}>{ts ? new Date(ts).toLocaleString() : '—'}</span>
          </div>
        ))}
      </div>

      <h3 className={styles.sectionTitle}>GitHub Actions Workflows</h3>
      <div className={styles.workflowGrid}>
        {workflows.map(wf => (
          <a key={wf.file} href={wf.html_url || '#'} target="_blank" rel="noreferrer" className={styles.wfCard}>
            <div className={styles.wfHeader}>
              <span className={styles.wfName}>{wf.name}</span>
              <span className={`${styles.wfStatus} ${styles['wf_' + (wf.conclusion || wf.status || 'no_runs')]}`}>
                {wf.conclusion || wf.status || 'no runs'}
              </span>
            </div>
            {wf.started_at && (
              <span className={styles.wfTs}>{new Date(wf.started_at).toLocaleString()}</span>
            )}
          </a>
        ))}
      </div>
    </div>
  )
}

function StatCard({ label, value, accent, warn }) {
  return (
    <div className={`${styles.statCard} ${accent ? styles.statAccent : ''} ${warn ? styles.statWarn : ''}`}>
      <span className={styles.statVal}>{value}</span>
      <span className={styles.statLabel}>{label}</span>
    </div>
  )
}

/* ── Outliers tab ──────────────────────────────────────────────────────────── */
function OutliersTab() {
  const [outliers, setOutliers] = useState([])
  const [loading,  setLoading]  = useState(true)
  const [error,    setError]    = useState(null)
  const [toast,    setToast]    = useState(null)

  const showToast = (msg, type = 'success') => {
    setToast({ msg, type })
    setTimeout(() => setToast(null), 3000)
  }

  useEffect(() => {
    getOutliers(100)
      .then(d => setOutliers(d.outliers || []))
      .catch(e => setError(e.message))
      .finally(() => setLoading(false))
  }, [])

  const handleIgnore = async (row) => {
    try {
      const result = await toggleIgnore(row.id)
      setOutliers(prev => prev.map(o => o.id === row.id ? { ...o, ignored: result.ignored } : o))
      showToast(result.ignored ? 'Price ignored — hidden from catalog' : 'Price restored')
    } catch (e) { showToast(e.message, 'error') }
  }

  if (loading) return <p className={pageStyles.status}>Detecting outliers…</p>
  if (error)   return <p className={pageStyles.error}>Error: {error}</p>

  return (
    <>
      {toast && <div className={`${styles.toast} ${styles[toast.type]}`}>{toast.msg}</div>}

      <p className={styles.helpText}>
        Prices where fair_value is &gt;5× the player's median across all their cards (minimum 3 cards).
        Ignoring a price hides it from the public catalog and future calculations.
      </p>

      {outliers.length === 0 ? (
        <p className={pageStyles.status}>No outliers detected.</p>
      ) : (
        <div className={styles.tableWrap}>
          <table className={styles.table}>
            <thead>
              <tr>
                <th className={styles.th}>Player</th>
                <th className={styles.th}>Sport</th>
                <th className={styles.th}>Year · Set</th>
                <th className={styles.th}>Variant</th>
                <th className={`${styles.th} ${styles.thRight}`}>Price</th>
                <th className={`${styles.th} ${styles.thRight}`}>Median</th>
                <th className={`${styles.th} ${styles.thRight}`}>Ratio</th>
                <th className={styles.th}>Sales</th>
                <th className={styles.th}></th>
              </tr>
            </thead>
            <tbody>
              {outliers.map(o => (
                <tr key={o.id} className={`${styles.tr} ${o.ignored ? styles.trIgnored : ''}`}>
                  <td className={styles.td}><strong>{o.player_name}</strong></td>
                  <td className={styles.td}>
                    <span className={`${styles.sportTag} ${styles['sport_' + o.sport]}`}>{o.sport}</span>
                  </td>
                  <td className={styles.td}>{o.year} · {o.set_name}</td>
                  <td className={styles.td}>
                    {o.variant !== 'Base' ? o.variant : <span className={styles.muted}>Base</span>}
                  </td>
                  <td className={`${styles.td} ${styles.thRight}`}>
                    <strong className={styles.danger}>${o.fair_value.toFixed(2)}</strong>
                  </td>
                  <td className={`${styles.td} ${styles.thRight}`}>${o.median_val.toFixed(2)}</td>
                  <td className={`${styles.td} ${styles.thRight}`}>
                    <span className={styles.ratioBadge}>{o.ratio}×</span>
                  </td>
                  <td className={styles.td}>{o.num_sales ?? '—'}</td>
                  <td className={styles.td}>
                    <button
                      className={o.ignored ? styles.restoreBtn : styles.ignoreBtn}
                      onClick={() => handleIgnore(o)}
                    >
                      {o.ignored ? 'Restore' : 'Ignore'}
                    </button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </>
  )
}
