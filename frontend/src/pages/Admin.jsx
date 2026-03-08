import { useState, useEffect, useCallback, useMemo } from 'react'
import {
  BarChart, Bar, XAxis, YAxis, Tooltip, ResponsiveContainer, Cell, CartesianGrid,
  LineChart, Line, ReferenceLine,
} from 'recharts'
import {
  getUsers, createUser, deleteUser, changePassword, changeRole,
  getPipelineHealth, getWorkflowStatus, getOutliers, toggleIgnore,
  getScrapeRuns, getScrapeRunsSummary, getDataQuality, getSnapshotAudit,
  getScrapeRunErrors,
  getSealedProductsAdmin, updateSealedProduct,
  triggerWorkflow, bulkIgnoreOutliers,
} from '../api/admin'
import { useAuth } from '../context/AuthContext'
import pageStyles from './Page.module.css'
import styles from './Admin.module.css'

const TABS = ['Users', 'Pipeline', 'Quality', 'Runs', 'Outliers', 'Sealed']

const WF_COLORS = ['#00d4aa', '#4a9eff', '#ff6b35', '#ffb332', '#a07ff0', '#e05555', '#3dba5e', '#ff9ff3']

export default function Admin() {
  const [tab, setTab] = useState('Users')
  const [activeCount, setActiveCount] = useState(0)

  // Poll for running scrapes every 30s to keep the badge current
  useEffect(() => {
    const check = () => {
      getScrapeRuns(50).then(d => {
        setActiveCount((d.runs || []).filter(r => r.status === 'running').length)
      }).catch(() => {})
    }
    check()
    const id = setInterval(check, 30000)
    return () => clearInterval(id)
  }, [])

  return (
    <div className={pageStyles.page}>
      <div className={pageStyles.header}>
        <h1 className={pageStyles.title}>Admin</h1>
        {activeCount > 0 && (
          <span className={styles.liveGlobalBadge}>
            <span className={styles.liveDotGlobal} />
            {activeCount} scrape{activeCount > 1 ? 's' : ''} running
          </span>
        )}
      </div>

      <div className={styles.tabRow}>
        {TABS.map(t => (
          <button
            key={t}
            className={`${styles.tabBtn} ${tab === t ? styles.tabBtnActive : ''}`}
            onClick={() => setTab(t)}
          >
            {t}
            {t === 'Runs' && activeCount > 0 && (
              <span className={styles.liveBadge}>{activeCount}</span>
            )}
          </button>
        ))}
      </div>

      {tab === 'Users'    && <UsersTab />}
      {tab === 'Pipeline' && <PipelineTab />}
      {tab === 'Quality'  && <QualityTab />}
      {tab === 'Runs'     && <RunsTab />}
      {tab === 'Outliers' && <OutliersTab />}
      {tab === 'Sealed'   && <SealedTab />}
    </div>
  )
}

/* ── Sealed Products tab ────────────────────────────────────────────────────── */
const SEALED_SPORTS = ['', 'NHL', 'NBA', 'NFL', 'MLB']

function SealedTab() {
  const [products, setProducts] = useState([])
  const [total,    setTotal]    = useState(0)
  const [pages,    setPages]    = useState(1)
  const [page,     setPage]     = useState(1)
  const [loading,  setLoading]  = useState(false)
  const [sport,    setSport]    = useState('')
  const [yearQ,    setYearQ]    = useState('')
  const [setQ,     setSetQ]     = useState('')
  const [editId,   setEditId]   = useState(null)
  const [editVals, setEditVals] = useState({})
  const [saving,   setSaving]   = useState(false)

  const load = useCallback(() => {
    setLoading(true)
    const params = { page, per_page: 50 }
    if (sport) params.sport    = sport
    if (yearQ) params.year     = yearQ
    if (setQ)  params.set_name = setQ
    getSealedProductsAdmin(params)
      .then(d => { setProducts(d.products || []); setTotal(d.total || 0); setPages(d.pages || 1) })
      .finally(() => setLoading(false))
  }, [page, sport, yearQ, setQ])

  useEffect(() => { load() }, [load])

  function startEdit(p) {
    setEditId(p.id)
    setEditVals({
      msrp:           p.msrp ?? '',
      cards_per_pack: p.cards_per_pack ?? '',
      packs_per_box:  p.packs_per_box  ?? '',
      release_date:   p.release_date   ?? '',
    })
  }
  function cancelEdit() { setEditId(null); setEditVals({}) }
  function saveEdit(id) {
    setSaving(true)
    const body = {}
    if (editVals.msrp !== '')           body.msrp           = parseFloat(editVals.msrp)
    if (editVals.cards_per_pack !== '') body.cards_per_pack = parseInt(editVals.cards_per_pack)
    if (editVals.packs_per_box  !== '') body.packs_per_box  = parseInt(editVals.packs_per_box)
    if (editVals.release_date   !== '') body.release_date   = editVals.release_date
    updateSealedProduct(id, body)
      .then(updated => {
        setProducts(ps => ps.map(p => p.id === id ? { ...p, ...updated } : p))
        setEditId(null)
      })
      .finally(() => setSaving(false))
  }

  return (
    <>
      <div style={{ display: 'flex', gap: 8, marginBottom: 14, flexWrap: 'wrap', alignItems: 'center' }}>
        {SEALED_SPORTS.map(s => (
          <button
            key={s || 'all'}
            className={`${styles.qualityPill} ${sport === s ? styles.qualityPillActive : ''}`}
            onClick={() => { setSport(s); setPage(1) }}
          >
            {s || 'All Sports'}
          </button>
        ))}
        <input
          className={styles.searchInput}
          placeholder="Year (e.g. 2024-25)"
          value={yearQ}
          onChange={e => { setYearQ(e.target.value); setPage(1) }}
          style={{ width: 140 }}
        />
        <input
          className={styles.searchInput}
          placeholder="Set name…"
          value={setQ}
          onChange={e => { setSetQ(e.target.value); setPage(1) }}
          style={{ width: 200 }}
        />
        <span className={styles.muted} style={{ fontSize: 12 }}>{total.toLocaleString()} products</span>
      </div>

      {loading ? (
        <div className={styles.muted}>Loading…</div>
      ) : products.length === 0 ? (
        <div className={styles.muted}>No sealed products found. Run the scrape_set_info workflow to populate.</div>
      ) : (
        <>
          <div className={styles.tableWrap}>
            <table className={styles.table}>
              <thead>
                <tr>
                  <th className={styles.th}>Sport</th>
                  <th className={styles.th}>Year</th>
                  <th className={styles.th}>Set Name</th>
                  <th className={styles.th}>Product</th>
                  <th className={`${styles.th} ${styles.thRight}`}>MSRP</th>
                  <th className={`${styles.th} ${styles.thRight}`}>Cards/Pack</th>
                  <th className={`${styles.th} ${styles.thRight}`}>Packs/Box</th>
                  <th className={styles.th}>Release</th>
                  <th className={styles.th} />
                </tr>
              </thead>
              <tbody>
                {products.map(p => {
                  const editing = editId === p.id
                  return (
                    <tr key={p.id} className={styles.tr}>
                      <td className={styles.td}><span className={styles.sportChip}>{p.sport}</span></td>
                      <td className={styles.td}>{p.year}</td>
                      <td className={styles.td} style={{ maxWidth: 220, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{p.set_name}</td>
                      <td className={styles.td}><span className={styles.muted}>{p.product_type}</span></td>
                      {editing ? (
                        <>
                          <td className={`${styles.td} ${styles.thRight}`}>
                            <input className={styles.inlineInput} value={editVals.msrp} onChange={e => setEditVals(v => ({...v, msrp: e.target.value}))} style={{width:64}} />
                          </td>
                          <td className={`${styles.td} ${styles.thRight}`}>
                            <input className={styles.inlineInput} value={editVals.cards_per_pack} onChange={e => setEditVals(v => ({...v, cards_per_pack: e.target.value}))} style={{width:44}} />
                          </td>
                          <td className={`${styles.td} ${styles.thRight}`}>
                            <input className={styles.inlineInput} value={editVals.packs_per_box} onChange={e => setEditVals(v => ({...v, packs_per_box: e.target.value}))} style={{width:44}} />
                          </td>
                          <td className={styles.td}>
                            <input className={styles.inlineInput} value={editVals.release_date} onChange={e => setEditVals(v => ({...v, release_date: e.target.value}))} style={{width:100}} placeholder="YYYY-MM-DD" />
                          </td>
                          <td className={styles.td} style={{ whiteSpace: 'nowrap' }}>
                            <button className={styles.saveBtn} onClick={() => saveEdit(p.id)} disabled={saving}>Save</button>
                            <button className={styles.cancelBtn} onClick={cancelEdit} style={{marginLeft:4}}>✕</button>
                          </td>
                        </>
                      ) : (
                        <>
                          <td className={`${styles.td} ${styles.thRight}`}>{p.msrp != null ? `$${p.msrp.toFixed(2)}` : <span className={styles.muted}>—</span>}</td>
                          <td className={`${styles.td} ${styles.thRight}`}>{p.cards_per_pack ?? <span className={styles.muted}>—</span>}</td>
                          <td className={`${styles.td} ${styles.thRight}`}>{p.packs_per_box ?? <span className={styles.muted}>—</span>}</td>
                          <td className={styles.td}>{p.release_date ?? <span className={styles.muted}>—</span>}</td>
                          <td className={styles.td}>
                            <button className={styles.editBtn} onClick={() => startEdit(p)}>Edit</button>
                          </td>
                        </>
                      )}
                    </tr>
                  )
                })}
              </tbody>
            </table>
          </div>
          {pages > 1 && (
            <div style={{ display: 'flex', gap: 6, marginTop: 14, flexWrap: 'wrap' }}>
              {Array.from({ length: pages }, (_, i) => i + 1).map(p => (
                <button
                  key={p}
                  className={`${styles.qualityPill} ${page === p ? styles.qualityPillActive : ''}`}
                  onClick={() => setPage(p)}
                >{p}</button>
              ))}
            </div>
          )}
        </>
      )}
    </>
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
  const [health,      setHealth]      = useState(null)
  const [workflows,   setWorkflows]   = useState([])
  const [loading,     setLoading]     = useState(true)
  const [refreshing,  setRefreshing]  = useState(false)
  const [error,       setError]       = useState(null)
  const [triggering,  setTriggering]  = useState(null)  // workflow file currently being triggered
  const [triggerMsg,  setTriggerMsg]  = useState(null)  // success/error message

  const load = useCallback((isRefresh = false) => {
    if (isRefresh) setRefreshing(true)
    else setLoading(true)
    Promise.all([getPipelineHealth(), getWorkflowStatus()])
      .then(([h, w]) => {
        setHealth(h)
        setWorkflows(w.workflows || [])
      })
      .catch(e => setError(e.message))
      .finally(() => { setLoading(false); setRefreshing(false) })
  }, [])

  useEffect(() => { load() }, [load])

  // Auto-refresh while GH Actions workflows are in progress
  useEffect(() => {
    const hasActive = workflows.some(w => w.status === 'in_progress' || w.status === 'queued')
    if (!hasActive) return
    const id = setInterval(() => load(true), 30000)
    return () => clearInterval(id)
  }, [workflows, load])

  const handleTrigger = async (wf) => {
    if (!confirm(`Trigger "${wf.name}"?\nThis will start a new GitHub Actions run.`)) return
    setTriggering(wf.file)
    setTriggerMsg(null)
    try {
      await triggerWorkflow(wf.file)
      setTriggerMsg({ type: 'success', text: `"${wf.name}" dispatched — check GitHub Actions.` })
    } catch (e) {
      setTriggerMsg({ type: 'error', text: e.message })
    } finally {
      setTriggering(null)
    }
  }

  if (loading) return <p className={pageStyles.status}>Loading pipeline data…</p>
  if (error)   return <p className={pageStyles.error}>Error: {error}</p>
  if (!health) return null

  return (
    <div className={styles.pipelineWrap}>

      <div className={styles.sectionHeaderRow}>
        <div className={styles.statCards} style={{ flex: 1 }}>
          <StatCard label="Catalog Size"    value={health.total_cards.toLocaleString()} />
          <StatCard label="Priced Cards"    value={health.priced_cards.toLocaleString()} />
          <StatCard label="Coverage"        value={`${health.coverage_pct}%`} accent={health.coverage_pct > 50} />
          <StatCard label="Priced (7d)"     value={(health.newly_priced_7d ?? 0).toLocaleString()} accent={(health.newly_priced_7d ?? 0) > 0} />
          <StatCard label="Priced (30d)"    value={(health.newly_priced_30d ?? 0).toLocaleString()} />
          <StatCard label="Ignored Prices"  value={health.ignored_count.toLocaleString()} warn={health.ignored_count > 0} />
          <StatCard label="Outlier Flags"   value={health.outlier_count.toLocaleString()} warn={health.outlier_count > 0} />
        </div>
        <button className={styles.refreshBtn} onClick={() => load(true)} disabled={refreshing}>
          {refreshing ? '↻' : '↻'} Refresh
        </button>
      </div>

      {triggerMsg && (
        <div className={`${styles.toast} ${styles[triggerMsg.type]}`}>{triggerMsg.text}</div>
      )}

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
          <div key={wf.file} className={styles.wfCard}>
            <div className={styles.wfHeader}>
              <a href={wf.html_url || '#'} target="_blank" rel="noreferrer" className={styles.wfName}>
                {wf.name}
              </a>
              <span className={`${styles.wfStatus} ${styles['wf_' + (wf.conclusion || wf.status || 'no_runs')]}`}>
                {wf.conclusion || wf.status || 'no runs'}
              </span>
            </div>
            {wf.started_at && (
              <span className={styles.wfTs}>{new Date(wf.started_at).toLocaleString()}</span>
            )}
            <button
              className={styles.triggerBtn}
              onClick={() => handleTrigger(wf)}
              disabled={triggering === wf.file}
              title={`Trigger ${wf.name}`}
            >
              {triggering === wf.file ? '…' : '▶ Run'}
            </button>
          </div>
        ))}
      </div>

    </div>
  )
}

/* ── Runs tab ──────────────────────────────────────────────────────────────── */
const ANOMALY_LABELS = {
  run_error:    'Run failed',
  timed_out:    'Timed out / killed',
  zero_delta:   'Zero Δ — no new prices',
  low_hit_rate: 'Low hit rate (<10%)',
  high_errors:  'High error count',
}

const DATE_RANGES = [
  { label: 'All', value: 'all' },
  { label: 'Last 7d', value: '7d' },
  { label: 'Last 30d', value: '30d' },
  { label: 'Last 90d', value: '90d' },
]

function RunsTab() {
  const [runs,       setRuns]       = useState([])
  const [summary,    setSummary]    = useState(null)
  const [loading,    setLoading]    = useState(true)
  const [refreshing, setRefreshing] = useState(false)
  const [error,      setError]      = useState(null)
  const [wfFilter,    setWfFilter]    = useState('')
  const [sportFilter, setSportFilter] = useState('')
  const [dateRange,   setDateRange]   = useState('all')
  const [errorRunId,  setErrorRunId]  = useState(null)
  const [runErrors,   setRunErrors]   = useState([])
  const [errLoading,  setErrLoading]  = useState(false)

  const load = useCallback((isRefresh = false) => {
    if (isRefresh) setRefreshing(true)
    else setLoading(true)
    Promise.all([getScrapeRuns(200), getScrapeRunsSummary()])
      .then(([rd, sd]) => { setRuns(rd.runs || []); setSummary(sd) })
      .catch(e => setError(e.message))
      .finally(() => { setLoading(false); setRefreshing(false) })
  }, [])

  useEffect(() => { load() }, [load])

  // Auto-refresh every 30s while any scrape is running
  const runningJobs = useMemo(() => runs.filter(r => r.status === 'running'), [runs])
  const [lastRefresh, setLastRefresh] = useState(Date.now())
  useEffect(() => {
    if (runningJobs.length === 0) return
    const id = setInterval(() => {
      setLastRefresh(Date.now())
      load(true)
    }, 30000)
    return () => clearInterval(id)
  }, [runningJobs.length, load])

  const uniqueWorkflows = useMemo(() => [...new Set(runs.map(r => r.workflow))].sort(), [runs])
  const uniqueSports    = useMemo(() => [...new Set(runs.map(r => r.sport).filter(Boolean))].sort(), [runs])

  const wfColor = useMemo(() => {
    const m = {}
    uniqueWorkflows.forEach((w, i) => { m[w] = WF_COLORS[i % WF_COLORS.length] })
    return m
  }, [uniqueWorkflows])

  const filteredRuns = useMemo(() => {
    const cutoff = dateRange === 'all' ? null
      : new Date(Date.now() - (dateRange === '7d' ? 7 : dateRange === '30d' ? 30 : 90) * 86400000)
    return runs.filter(r =>
      (!wfFilter    || r.workflow === wfFilter) &&
      (!sportFilter || r.sport    === sportFilter) &&
      (!cutoff      || new Date(r.started_at) >= cutoff)
    )
  }, [runs, wfFilter, sportFilter, dateRange])

  const chartData = useMemo(() =>
    [...filteredRuns].reverse().slice(-60).map(r => ({
      date:     new Date(r.started_at).toLocaleDateString('en-CA', { month: 'short', day: 'numeric' }),
      delta:    r.cards_delta,
      hitRate:  r.cards_total > 0 ? Math.round(r.cards_found / r.cards_total * 100) : null,
      workflow: r.workflow,
    })), [filteredRuns]
  )

  const kpis = useMemo(() => {
    if (!summary) return null
    const wfs = wfFilter ? summary.workflows.filter(w => w.workflow === wfFilter) : summary.workflows
    const totalRuns   = wfs.reduce((s, w) => s + w.total_runs, 0)
    const successRuns = wfs.reduce((s, w) => s + w.success_runs, 0)
    const hitRates    = wfs.filter(w => w.avg_hit_rate != null).map(w => w.avg_hit_rate)
    return {
      totalRuns,
      successRate:  totalRuns > 0 ? Math.round(successRuns / totalRuns * 100) : 0,
      avgHitRate:   hitRates.length > 0 ? Math.round(hitRates.reduce((s, v) => s + v, 0) / hitRates.length) : null,
      totalDelta:   wfs.reduce((s, w) => s + w.total_delta, 0),
      totalErrors:  wfs.reduce((s, w) => s + w.total_errors, 0),
      anomalyCount: (wfFilter ? summary.anomalies.filter(a => a.workflow === wfFilter) : summary.anomalies).length,
    }
  }, [summary, wfFilter])

  const visibleAnomalies = useMemo(() => {
    if (!summary) return []
    return wfFilter ? summary.anomalies.filter(a => a.workflow === wfFilter) : summary.anomalies
  }, [summary, wfFilter])

  if (loading) return <p className={pageStyles.status}>Loading runs…</p>
  if (error)   return <p className={pageStyles.error}>Error: {error}</p>

  return (
    <div className={styles.runsWrap}>

      {/* Active jobs banner */}
      {runningJobs.length > 0 && (
        <div className={styles.activeJobsBanner}>
          <div className={styles.liveHeader}>
            <div className={styles.liveIndicator}>
              <span className={styles.liveDot} />
              <span className={styles.liveText}>
                Live — {runningJobs.length} job{runningJobs.length > 1 ? 's' : ''} running · auto-refreshing every 30s
              </span>
            </div>
            <span className={styles.muted} style={{ fontSize: 11 }}>
              Last updated: {new Date(lastRefresh).toLocaleTimeString()}
            </span>
          </div>
          <div className={styles.activeJobsGrid}>
            {runningJobs.map(r => {
              const elapsed = r.started_at
                ? Math.round((Date.now() - new Date(r.started_at)) / 60000)
                : null
              const processed = r.cards_processed ?? 0
              const total     = r.cards_total ?? 0
              const found     = r.cards_found ?? 0
              const progress  = total > 0 ? Math.round(processed / total * 100) : 0
              const hitRate   = processed > 0 ? Math.round(found / processed * 100) : null
              const rate      = (elapsed != null && elapsed > 0 && processed > 0)
                ? Math.round(processed / elapsed * 60) : null
              const eta = (elapsed != null && rate > 0 && processed < total)
                ? Math.round((total - processed) / rate)
                : null
              return (
                <div key={r.id} className={styles.activeJobCard}>
                  <div className={styles.activeJobHeader}>
                    <span className={styles.running}>⬤</span>
                    <span className={styles.activeJobWf}>{r.workflow}</span>
                    {r.sport && <span className={styles.activeJobSport}>{r.sport}</span>}
                    {r.tier  && <span className={`${styles.tierBadge} ${styles['tier_' + r.tier]}`}>{r.tier}</span>}
                  </div>
                  <div className={styles.activeJobStats}>
                    <span><strong>{processed.toLocaleString()}</strong> / {total.toLocaleString()} processed</span>
                    <span><strong>{found.toLocaleString()}</strong> found</span>
                    {hitRate != null && (
                      <span className={hitRate < 10 ? styles.textDanger : hitRate < 30 ? styles.textWarn : styles.textSuccess}>
                        {hitRate}% hit
                      </span>
                    )}
                    {r.errors > 0 && <span className={styles.textDanger}>{r.errors} err</span>}
                    {rate != null && <span className={styles.muted}>{rate.toLocaleString()}/hr</span>}
                    {elapsed != null && <span className={styles.muted}>{elapsed}m elapsed</span>}
                    {eta != null && <span className={styles.muted}>~{eta}m left</span>}
                  </div>
                  {total > 0 && (
                    <div className={styles.progressBar}>
                      <div className={styles.progressFill} style={{ width: `${Math.min(progress, 100)}%` }} />
                      <span className={styles.progressLabel}>{progress}%</span>
                    </div>
                  )}
                </div>
              )
            })}
          </div>
        </div>
      )}

      {/* Filter bar */}
      <div className={styles.runsFilterBar}>
        <select className={styles.runsSelect} value={wfFilter} onChange={e => setWfFilter(e.target.value)}>
          <option value="">All Workflows</option>
          {uniqueWorkflows.map(w => <option key={w} value={w}>{w}</option>)}
        </select>
        <select className={styles.runsSelect} value={sportFilter} onChange={e => setSportFilter(e.target.value)}>
          <option value="">All Sports</option>
          {uniqueSports.map(s => <option key={s} value={s}>{s}</option>)}
        </select>
        <div className={styles.dateRangePills}>
          {DATE_RANGES.map(d => (
            <button
              key={d.value}
              className={`${styles.dateRangePill} ${dateRange === d.value ? styles.dateRangePillActive : ''}`}
              onClick={() => setDateRange(d.value)}
            >{d.label}</button>
          ))}
        </div>
        {(wfFilter || sportFilter) && (
          <button className={styles.clearFilterBtn} onClick={() => { setWfFilter(''); setSportFilter('') }}>Clear</button>
        )}
        <span className={styles.runsCount}>{filteredRuns.length} runs</span>
        <button
          className={styles.refreshBtn}
          onClick={() => load(true)}
          disabled={refreshing}
          title="Refresh"
        >{refreshing ? '↻' : '↻'} Refresh</button>
      </div>

      {/* KPI strip */}
      {kpis && (
        <div className={styles.kpiStrip}>
          <KpiCard label="Total Runs"   value={kpis.totalRuns} />
          <KpiCard label="Success Rate" value={`${kpis.successRate}%`} accent={kpis.successRate >= 90} warn={kpis.successRate < 75} />
          <KpiCard label="Avg Hit Rate" value={kpis.avgHitRate != null ? `${kpis.avgHitRate}%` : '—'} warn={kpis.avgHitRate != null && kpis.avgHitRate < 30} />
          <KpiCard label="Total Δ"      value={kpis.totalDelta.toLocaleString()} />
          <KpiCard label="Errors"       value={kpis.totalErrors.toLocaleString()} warn={kpis.totalErrors > 0} />
          <KpiCard label="Anomalies"    value={kpis.anomalyCount} warn={kpis.anomalyCount > 0} />
        </div>
      )}

      {/* Workflow health cards */}
      {summary && summary.workflows.length > 0 && (
        <>
          <h3 className={styles.sectionTitle}>Workflow Health</h3>
          <div className={styles.wfHealthGrid}>
            {summary.workflows.map(w => {
              const isSelected = wfFilter === w.workflow
              const daysSince = w.last_run_at
                ? Math.floor((Date.now() - new Date(w.last_run_at)) / 86400000)
                : null
              // Infer expected cadence from workflow name
              const cadenceDays = /daily/i.test(w.workflow) ? 1
                : /monthly/i.test(w.workflow) ? 31
                : /weekly|stars|graded|premium|base/i.test(w.workflow) ? 7
                : null
              const isOverdue = cadenceDays != null && daysSince != null
                && daysSince > cadenceDays * 1.5
              const consecFail = w.consecutive_errors ?? 0
              const dotClass = consecFail >= 2 || w.last_run_status === 'error' ? 'error'
                : (isOverdue || w.zero_delta_runs > 0 || w.success_rate < 75) ? 'warn'
                : 'healthy'
              return (
                <div
                  key={w.workflow}
                  className={`${styles.wfHealthCard} ${isSelected ? styles.wfHealthSelected : ''}`}
                  onClick={() => setWfFilter(isSelected ? '' : w.workflow)}
                >
                  <div className={styles.wfHealthHeader}>
                    <span className={`${styles.statusDot} ${styles['dot_' + dotClass]}`} />
                    <span className={styles.wfHealthName}>{w.workflow}</span>
                    {consecFail >= 2 && (
                      <span className={styles.consecBadge} title={`${consecFail} consecutive failures`}>
                        ✕{consecFail}
                      </span>
                    )}
                    {isOverdue && consecFail < 2 && (
                      <span className={styles.overdueBadge} title={`Expected every ${cadenceDays}d — last ran ${daysSince}d ago`}>
                        overdue
                      </span>
                    )}
                  </div>
                  <div className={styles.wfHealthMeta}>
                    <span>{w.total_runs} runs</span>
                    <span className={w.success_rate >= 90 ? styles.textSuccess : w.success_rate < 75 ? styles.textDanger : ''}>
                      {w.success_rate}% ok
                    </span>
                    {w.avg_hit_rate != null && (
                      <span className={w.avg_hit_rate < 30 ? styles.textWarn : ''}>{w.avg_hit_rate}% hit</span>
                    )}
                    {w.zero_delta_runs > 0 && (
                      <span className={styles.textWarn}>{w.zero_delta_runs} Δ=0</span>
                    )}
                  </div>
                  <div className={styles.wfHealthFooter}>
                    <span>
                      {daysSince === 0 ? 'Today' : daysSince === 1 ? 'Yesterday'
                        : daysSince != null ? `${daysSince}d ago` : 'Never'}
                      {cadenceDays && <span className={styles.muted}> (/{cadenceDays}d)</span>}
                    </span>
                    {w.last_run_status && (
                      <span className={`${styles.wfStatus} ${styles['wf_' + w.last_run_status]}`}>
                        {w.last_run_status}
                      </span>
                    )}
                  </div>
                </div>
              )
            })}
          </div>
        </>
      )}

      {/* Two charts side by side */}
      {chartData.length > 0 && (
        <div className={styles.chartsRow}>
          <div className={styles.chartBox}>
            <div className={styles.chartTitle}>Delta Volume Per Run</div>
            <ResponsiveContainer width="100%" height={180}>
              <BarChart data={chartData} margin={{ top: 4, right: 8, left: 0, bottom: 4 }}>
                <CartesianGrid strokeDasharray="3 3" stroke="rgba(255,255,255,0.05)" vertical={false} />
                <XAxis dataKey="date" tick={{ fontSize: 10, fill: 'var(--text-muted)' }} axisLine={false} tickLine={false} interval="preserveStartEnd" />
                <YAxis tick={{ fontSize: 10, fill: 'var(--text-muted)' }} axisLine={false} tickLine={false} width={36} />
                <Tooltip
                  contentStyle={{ background: 'var(--bg-card)', border: '1px solid var(--border)', borderRadius: 8, fontSize: 12 }}
                  itemStyle={{ color: 'var(--text-primary)' }} labelStyle={{ color: 'var(--text-muted)', marginBottom: 4 }}
                  formatter={v => [v.toLocaleString(), 'Δ updates']}
                />
                <Bar dataKey="delta" radius={[3, 3, 0, 0]} maxBarSize={20}>
                  {chartData.map((d, i) => <Cell key={i} fill={wfColor[d.workflow] || '#00d4aa'} />)}
                </Bar>
              </BarChart>
            </ResponsiveContainer>
          </div>
          <div className={styles.chartBox}>
            <div className={styles.chartTitle}>Hit Rate % Per Run</div>
            <ResponsiveContainer width="100%" height={180}>
              <LineChart data={chartData} margin={{ top: 4, right: 8, left: 0, bottom: 4 }}>
                <CartesianGrid strokeDasharray="3 3" stroke="rgba(255,255,255,0.05)" vertical={false} />
                <XAxis dataKey="date" tick={{ fontSize: 10, fill: 'var(--text-muted)' }} axisLine={false} tickLine={false} interval="preserveStartEnd" />
                <YAxis domain={[0, 100]} tick={{ fontSize: 10, fill: 'var(--text-muted)' }} axisLine={false} tickLine={false} width={36} tickFormatter={v => `${v}%`} />
                <Tooltip
                  contentStyle={{ background: 'var(--bg-card)', border: '1px solid var(--border)', borderRadius: 8, fontSize: 12 }}
                  itemStyle={{ color: 'var(--text-primary)' }} labelStyle={{ color: 'var(--text-muted)', marginBottom: 4 }}
                  formatter={v => [`${v}%`, 'Hit Rate']}
                />
                <ReferenceLine y={30} stroke="rgba(255,179,50,0.4)" strokeDasharray="4 4" />
                <Line type="monotone" dataKey="hitRate" stroke="#00d4aa" strokeWidth={1.5} dot={false} connectNulls={false} />
              </LineChart>
            </ResponsiveContainer>
          </div>
        </div>
      )}

      {/* Anomaly feed */}
      {visibleAnomalies.length > 0 && (
        <>
          <h3 className={styles.sectionTitle}>Anomalies Detected ({visibleAnomalies.length})</h3>
          <div className={styles.anomalyFeed}>
            {visibleAnomalies.slice(0, 15).map(a => (
              <div key={a.id} className={`${styles.anomalyRow} ${styles['anomaly_' + a.reason]}`}>
                <span className={styles.anomalyLabel}>{ANOMALY_LABELS[a.reason] || a.reason}</span>
                <span className={styles.anomalyDetail}>
                  <strong>{a.workflow}</strong>{a.sport && <> · {a.sport}</>}{a.tier && <> · {a.tier}</>}
                </span>
                <span className={styles.anomalyTs}>{a.started_at ? new Date(a.started_at).toLocaleString() : '—'}</span>
                <span className={styles.anomalyStats}>
                  {a.cards_total > 0 && <>{a.cards_found}/{a.cards_total} found · </>}Δ {a.cards_delta}{a.errors > 0 && <> · {a.errors} err</>}
                </span>
              </div>
            ))}
          </div>
        </>
      )}

      {/* Run history table */}
      <h3 className={styles.sectionTitle}>Run History</h3>
      {filteredRuns.length === 0 ? (
        <p className={pageStyles.status}>No runs match the current filters.</p>
      ) : (
        <div className={styles.tableWrap}>
          <table className={styles.table}>
            <thead>
              <tr>
                <th className={styles.th}>Workflow</th>
                <th className={styles.th}>Sport</th>
                <th className={styles.th}>Tier</th>
                <th className={styles.th}>Mode</th>
                <th className={styles.th}>Started</th>
                <th className={styles.th}>Dur</th>
                <th className={`${styles.th} ${styles.thRight}`}>Total</th>
                <th className={`${styles.th} ${styles.thRight}`}>Found</th>
                <th className={`${styles.th} ${styles.thRight}`}>Hit%</th>
                <th className={`${styles.th} ${styles.thRight}`}>Δ</th>
                <th className={`${styles.th} ${styles.thRight}`}>Err</th>
                <th className={styles.th}>Status</th>
              </tr>
            </thead>
            <tbody>
              {filteredRuns.map(r => {
                const duration = r.finished_at && r.started_at
                  ? Math.round((new Date(r.finished_at) - new Date(r.started_at)) / 60000) : null
                const hitRate = r.cards_total > 0
                  ? Math.round(r.cards_found / r.cards_total * 100) : null
                const isError = r.status === 'error'
                const isWarn  = !isError && (
                  (r.status === 'completed' && r.cards_delta === 0 && r.cards_total > 0) ||
                  (hitRate != null && hitRate < 10) || r.errors > 10
                )
                return (
                  <tr key={r.id} className={`${styles.tr} ${isError ? styles.trError : isWarn ? styles.trWarn : ''}`}>
                    <td className={styles.td}>
                      <span className={styles.runWorkflow} style={{ color: wfColor[r.workflow] }}>{r.workflow}</span>
                    </td>
                    <td className={styles.td}>{r.sport || <span className={styles.muted}>all</span>}</td>
                    <td className={styles.td}>
                      {r.tier ? <span className={`${styles.tierBadge} ${styles['tier_' + r.tier]}`}>{r.tier}</span>
                              : <span className={styles.muted}>—</span>}
                    </td>
                    <td className={styles.td}>
                      <span className={`${styles.modeBadge} ${r.mode === 'graded' ? styles.modeGraded : ''}`}>{r.mode}</span>
                    </td>
                    <td className={styles.td}>{r.started_at ? new Date(r.started_at).toLocaleString() : '—'}</td>
                    <td className={styles.td}>
                      {duration != null ? `${duration}m` : r.status === 'running' ? <span className={styles.running}>running…</span> : '—'}
                    </td>
                    <td className={`${styles.td} ${styles.thRight}`}>{r.cards_total.toLocaleString()}</td>
                    <td className={`${styles.td} ${styles.thRight}`}>{r.cards_found.toLocaleString()}</td>
                    <td className={`${styles.td} ${styles.thRight}`}>
                      {hitRate != null
                        ? <span className={hitRate < 10 ? styles.textDanger : hitRate < 30 ? styles.textWarn : styles.textSuccess}>{hitRate}%</span>
                        : <span className={styles.muted}>—</span>}
                    </td>
                    <td className={`${styles.td} ${styles.thRight}`}>
                      {r.cards_delta === 0 && r.status === 'completed' && r.cards_total > 0
                        ? <span className={styles.textWarn}>0</span>
                        : r.cards_delta.toLocaleString()}
                    </td>
                    <td className={`${styles.td} ${styles.thRight}`}>
                      {r.errors > 0 ? (
                        <button
                          className={styles.errCountBtn}
                          onClick={() => {
                            if (errorRunId === r.id) { setErrorRunId(null); return }
                            setErrorRunId(r.id); setRunErrors([]); setErrLoading(true)
                            getScrapeRunErrors(r.id).then(d => setRunErrors(d.errors || [])).finally(() => setErrLoading(false))
                          }}
                          title="Click to see error details"
                        >
                          {r.errors}
                        </button>
                      ) : r.errors}
                    </td>
                    <td className={styles.td}>
                      <span className={`${styles.wfStatus} ${styles['wf_' + r.status]}`}>{r.status}</span>
                    </td>
                  </tr>
                )
              })}
            </tbody>
          </table>
        </div>
      )}

      {/* Error drill-down panel */}
      {errorRunId && (
        <div className={styles.errorPanel}>
          <div className={styles.errorPanelHeader}>
            <span>Error log — run #{errorRunId}</span>
            <button className={styles.cancelBtn} onClick={() => setErrorRunId(null)} style={{padding:'2px 8px',fontSize:11}}>✕</button>
          </div>
          {errLoading ? (
            <div className={styles.muted} style={{padding:'10px 14px'}}>Loading…</div>
          ) : runErrors.length === 0 ? (
            <div className={styles.muted} style={{padding:'10px 14px'}}>No error details available (errors logged from next scrape onwards).</div>
          ) : (
            <table className={styles.table} style={{marginTop:0}}>
              <thead>
                <tr>
                  <th className={styles.th}>Card</th>
                  <th className={styles.th}>Error Type</th>
                  <th className={styles.th}>Message</th>
                  <th className={styles.th}>Time</th>
                </tr>
              </thead>
              <tbody>
                {runErrors.map(e => (
                  <tr key={e.id} className={styles.tr}>
                    <td className={styles.td} style={{maxWidth:220,overflow:'hidden',textOverflow:'ellipsis',whiteSpace:'nowrap'}}>{e.card_name}</td>
                    <td className={styles.td}><span className={styles.textDanger}>{e.error_type}</span></td>
                    <td className={styles.td} style={{maxWidth:320,overflow:'hidden',textOverflow:'ellipsis',whiteSpace:'nowrap',fontSize:11,color:'var(--text-muted)'}}>{e.error_msg}</td>
                    <td className={styles.td} style={{whiteSpace:'nowrap'}}>{e.occurred_at?.slice(0,19).replace('T',' ')}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </div>
      )}
    </div>
  )
}

/* ── Quality tab ────────────────────────────────────────────────────────────── */
function QualityTab() {
  const [data,       setData]       = useState(null)
  const [loading,    setLoading]    = useState(true)
  const [refreshing, setRefreshing] = useState(false)
  const [error,      setError]      = useState(null)
  const [view,       setView]       = useState('stale')

  const load = useCallback((isRefresh = false) => {
    if (isRefresh) setRefreshing(true)
    else setLoading(true)
    getDataQuality()
      .then(d => setData(d))
      .catch(e => setError(e.message))
      .finally(() => { setLoading(false); setRefreshing(false) })
  }, [])

  useEffect(() => { load() }, [load])

  if (loading) return <p className={pageStyles.status}>Loading quality data…</p>
  if (error)   return <p className={pageStyles.error}>Error: {error}</p>
  if (!data)   return null

  const { stats, freshness_by_tier, stale_cards, low_confidence_cards } = data

  return (
    <div className={styles.qualityWrap}>

      {/* KPI strip */}
      <div className={styles.sectionHeaderRow}>
      <div className={styles.kpiStrip} style={{ flex: 1 }}>
        <KpiCard label="Stale >30d"      value={stats.stale_30.toLocaleString()}      warn={stats.stale_30 > 100} />
        <KpiCard label="Stale >90d"      value={stats.stale_90.toLocaleString()}      warn={stats.stale_90 > 50} />
        <KpiCard label="Never Scraped"   value={stats.never_scraped.toLocaleString()} warn={stats.never_scraped > 0} />
        <KpiCard label="Single Sale"     value={stats.single_sale.toLocaleString()}   warn={stats.single_sale > 50} />
        <KpiCard label="Low Confidence"  value={stats.low_confidence.toLocaleString()} warn={stats.low_confidence > 100} />
        <KpiCard label="Zero Price"      value={stats.zero_price.toLocaleString()}    warn={stats.zero_price > 0} />
      </div>
      <button className={styles.refreshBtn} onClick={() => load(true)} disabled={refreshing}>
        {refreshing ? '↻' : '↻'} Refresh
      </button>
      </div>

      {/* Freshness by tier */}
      <h3 className={styles.sectionTitle}>Price Freshness by Tier</h3>
      <div className={styles.tableWrap}>
        <table className={styles.table}>
          <thead>
            <tr>
              <th className={styles.th}>Tier</th>
              <th className={`${styles.th} ${styles.thRight}`}>Total</th>
              <th className={`${styles.th} ${styles.thRight}`}>Fresh &lt;7d</th>
              <th className={`${styles.th} ${styles.thRight}`}>7–30d</th>
              <th className={`${styles.th} ${styles.thRight}`}>Stale &gt;30d</th>
              <th className={styles.th}>Distribution</th>
            </tr>
          </thead>
          <tbody>
            {freshness_by_tier.map(t => {
              const total = t.total || 1
              const pctFresh  = Math.round(t.fresh_7d  / total * 100)
              const pctRecent = Math.round(t.fresh_30d / total * 100)
              const pctStale  = Math.round(t.stale     / total * 100)
              return (
                <tr key={t.tier} className={styles.tr}>
                  <td className={styles.td}>
                    <span className={`${styles.tierBadge} ${styles['tier_' + t.tier]}`}>{t.tier}</span>
                  </td>
                  <td className={`${styles.td} ${styles.thRight}`}>{t.total.toLocaleString()}</td>
                  <td className={`${styles.td} ${styles.thRight} ${styles.textSuccess}`}>{t.fresh_7d.toLocaleString()}</td>
                  <td className={`${styles.td} ${styles.thRight}`} style={{ color: '#ffb332' }}>{t.fresh_30d.toLocaleString()}</td>
                  <td className={`${styles.td} ${styles.thRight} ${t.stale > 0 ? styles.textDanger : ''}`}>{t.stale.toLocaleString()}</td>
                  <td className={styles.td}>
                    <div className={styles.freshnessBar}>
                      <div className={`${styles.freshSeg} ${styles.freshGreen}`}  style={{ width: `${pctFresh}%` }}  title={`Fresh: ${pctFresh}%`} />
                      <div className={`${styles.freshSeg} ${styles.freshYellow}`} style={{ width: `${pctRecent}%` }} title={`Recent: ${pctRecent}%`} />
                      <div className={`${styles.freshSeg} ${styles.freshRed}`}    style={{ width: `${pctStale}%` }}  title={`Stale: ${pctStale}%`} />
                    </div>
                  </td>
                </tr>
              )
            })}
          </tbody>
        </table>
      </div>

      {/* Sub-view toggle */}
      <div className={styles.qualityToggle}>
        <button
          className={`${styles.qualityPill} ${view === 'stale' ? styles.qualityPillActive : ''}`}
          onClick={() => setView('stale')}
        >Priority Stale ({stale_cards.length})</button>
        <button
          className={`${styles.qualityPill} ${view === 'lowconf' ? styles.qualityPillActive : ''}`}
          onClick={() => setView('lowconf')}
        >Low Confidence ({low_confidence_cards.length})</button>
        <button
          className={`${styles.qualityPill} ${view === 'snapshot' ? styles.qualityPillActive : ''}`}
          onClick={() => setView('snapshot')}
        >Snapshot Audit</button>
      </div>

      {/* Stale cards table */}
      {view === 'stale' && (
        <>
          <p className={styles.helpText}>
            Staple &amp; premium cards not scraped in over 30 days — highest priority to re-scrape. Sorted oldest first.
          </p>
          <QualityCardTable cards={stale_cards} showStaleness />
        </>
      )}

      {/* Low confidence table */}
      {view === 'lowconf' && (
        <>
          <p className={styles.helpText}>
            Cards with only 1 eBay sale driving the price (fair_value &gt; $5). These prices are less reliable and should be scraped again when possible.
          </p>
          <QualityCardTable cards={low_confidence_cards} />
        </>
      )}

      {/* Snapshot audit */}
      {view === 'snapshot' && <SnapshotAuditView />}
    </div>
  )
}

const AUDIT_TIERS   = ['staple', 'premium', 'stars', 'base']
const AUDIT_SPORTS  = ['', 'NHL', 'NBA', 'NFL', 'MLB']

function SnapshotAuditView() {
  const [cards,   setCards]   = useState([])
  const [loading, setLoading] = useState(true)
  const [error,   setError]   = useState(null)
  const [tier,    setTier]    = useState('staple')
  const [sport,   setSport]   = useState('')
  const [expanded, setExpanded] = useState(null)

  const load = useCallback((t, s) => {
    setLoading(true)
    setError(null)
    getSnapshotAudit(t, s || null, 25)
      .then(d => setCards(d.cards || []))
      .catch(e => setError(e.message))
      .finally(() => setLoading(false))
  }, [])

  useEffect(() => { load(tier, sport) }, [tier, sport, load])

  return (
    <div>
      <p className={styles.helpText}>
        Last 5 price snapshots per card. Verify ETL is accumulating history correctly and prices are moving as expected.
      </p>

      {/* Filters */}
      <div style={{ display: 'flex', gap: 8, marginBottom: 14, flexWrap: 'wrap' }}>
        <div className={styles.qualityToggle} style={{ margin: 0 }}>
          {AUDIT_TIERS.map(t => (
            <button key={t}
              className={`${styles.qualityPill} ${tier === t ? styles.qualityPillActive : ''}`}
              onClick={() => setTier(t)}
            >{t}</button>
          ))}
        </div>
        <div className={styles.qualityToggle} style={{ margin: 0 }}>
          {AUDIT_SPORTS.map(s => (
            <button key={s || 'all'}
              className={`${styles.qualityPill} ${sport === s ? styles.qualityPillActive : ''}`}
              onClick={() => setSport(s)}
            >{s || 'All'}</button>
          ))}
        </div>
      </div>

      {loading && <p className={pageStyles.status}>Loading…</p>}
      {error   && <p className={pageStyles.error}>Error: {error}</p>}

      {!loading && !error && (
        <div className={styles.tableWrap}>
          <table className={styles.table}>
            <thead>
              <tr>
                <th className={styles.th}>Player</th>
                <th className={styles.th}>Set · Year</th>
                <th className={styles.th}>Variant</th>
                <th className={`${styles.th} ${styles.thRight}`}>Current $</th>
                <th className={styles.th}>Last 5 Snapshots</th>
              </tr>
            </thead>
            <tbody>
              {cards.map(c => {
                const isExp = expanded === c.id
                return (
                  <tr key={c.id} className={styles.tr}
                    style={{ cursor: 'pointer' }}
                    onClick={() => setExpanded(isExp ? null : c.id)}
                  >
                    <td className={styles.td}><strong>{c.player_name}</strong></td>
                    <td className={styles.td}>{c.set_name} · {c.year}</td>
                    <td className={styles.td}>
                      {c.variant !== 'Base' ? c.variant : <span className={styles.muted}>Base</span>}
                    </td>
                    <td className={`${styles.td} ${styles.thRight}`}>
                      ${c.current_value != null ? c.current_value.toFixed(2) : '—'}
                    </td>
                    <td className={styles.td}>
                      {c.snapshots.length === 0 ? (
                        <span className={styles.textDanger}>No history</span>
                      ) : (
                        <div className={styles.snapshotRow}>
                          {c.snapshots.map((sn, si) => (
                            <span key={si} className={styles.snapshotChip}
                              title={sn.scraped_at}
                            >
                              ${sn.fair_value?.toFixed(2) ?? '—'}
                            </span>
                          ))}
                          {isExp && (
                            <div className={styles.snapshotDetail}>
                              {c.snapshots.map((sn, si) => (
                                <div key={si} className={styles.snapshotDetailRow}>
                                  <span className={styles.muted}>{sn.scraped_at}</span>
                                  <span>${sn.fair_value?.toFixed(2) ?? '—'}</span>
                                  <span className={styles.muted}>{sn.num_sales} sale{sn.num_sales !== 1 ? 's' : ''}</span>
                                </div>
                              ))}
                            </div>
                          )}
                        </div>
                      )}
                    </td>
                  </tr>
                )
              })}
            </tbody>
          </table>
        </div>
      )}
    </div>
  )
}

function QualityCardTable({ cards, showStaleness }) {
  if (cards.length === 0) return <p className={pageStyles.status}>No items.</p>

  const daysSince = (ts) => {
    if (!ts) return null
    return Math.floor((Date.now() - new Date(ts)) / 86400000)
  }

  return (
    <div className={styles.tableWrap}>
      <table className={styles.table}>
        <thead>
          <tr>
            <th className={styles.th}>Player</th>
            <th className={styles.th}>Sport</th>
            <th className={styles.th}>Year · Set</th>
            <th className={styles.th}>Variant</th>
            <th className={styles.th}>Tier</th>
            <th className={`${styles.th} ${styles.thRight}`}>Price</th>
            <th className={`${styles.th} ${styles.thRight}`}>Sales</th>
            <th className={styles.th}>{showStaleness ? 'Last Scraped' : 'Scraped'}</th>
          </tr>
        </thead>
        <tbody>
          {cards.map((c, i) => {
            const age = daysSince(c.scraped_at)
            return (
              <tr key={i} className={styles.tr}>
                <td className={styles.td}><strong>{c.player_name}</strong></td>
                <td className={styles.td}>
                  <span className={`${styles.sportTag} ${styles['sport_' + c.sport]}`}>{c.sport}</span>
                </td>
                <td className={styles.td}>{c.year} · {c.set_name}</td>
                <td className={styles.td}>
                  {c.variant !== 'Base' ? c.variant : <span className={styles.muted}>Base</span>}
                </td>
                <td className={styles.td}>
                  <span className={`${styles.tierBadge} ${styles['tier_' + c.scrape_tier]}`}>{c.scrape_tier}</span>
                </td>
                <td className={`${styles.td} ${styles.thRight}`}>${c.fair_value.toFixed(2)}</td>
                <td className={`${styles.td} ${styles.thRight}`}>
                  <span className={c.num_sales === 1 ? styles.textWarn : ''}>{c.num_sales ?? '—'}</span>
                </td>
                <td className={styles.td}>
                  {c.scraped_at ? (
                    <span className={showStaleness && age > 60 ? styles.textDanger : showStaleness && age > 30 ? styles.textWarn : ''}>
                      {age != null ? `${age}d ago` : '—'}
                    </span>
                  ) : <span className={styles.textDanger}>Never</span>}
                </td>
              </tr>
            )
          })}
        </tbody>
      </table>
    </div>
  )
}

function KpiCard({ label, value, accent, warn }) {
  return (
    <div className={`${styles.kpiCard} ${accent ? styles.kpiAccent : ''} ${warn ? styles.kpiWarn : ''}`}>
      <span className={styles.kpiVal}>{value}</span>
      <span className={styles.kpiLabel}>{label}</span>
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
  const [outliers,    setOutliers]    = useState([])
  const [loading,     setLoading]     = useState(true)
  const [error,       setError]       = useState(null)
  const [toast,       setToast]       = useState(null)
  const [bulkIgnoring, setBulkIgnoring] = useState(false)

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

  const handleIgnoreAll = async () => {
    const activeIds = outliers.filter(o => !o.ignored).map(o => o.id)
    if (!activeIds.length) return
    if (!confirm(`Ignore all ${activeIds.length} active outlier prices? This hides them from the public catalog.`)) return
    setBulkIgnoring(true)
    try {
      const result = await bulkIgnoreOutliers(activeIds)
      setOutliers(prev => prev.map(o => activeIds.includes(o.id) ? { ...o, ignored: true } : o))
      showToast(`${result.ignored} prices ignored`)
    } catch (e) { showToast(e.message, 'error') }
    finally { setBulkIgnoring(false) }
  }

  if (loading) return <p className={pageStyles.status}>Detecting outliers…</p>
  if (error)   return <p className={pageStyles.error}>Error: {error}</p>

  const activeCount = outliers.filter(o => !o.ignored).length

  return (
    <>
      {toast && <div className={`${styles.toast} ${styles[toast.type]}`}>{toast.msg}</div>}

      <div className={styles.sectionHeaderRow} style={{ marginBottom: 10 }}>
        <p className={styles.helpText} style={{ margin: 0 }}>
          Prices &gt;5× the player's median (min 3 cards). The nightly quarantine auto-ignores prices &gt;3×.
          Manual review here catches borderline cases.
        </p>
        {activeCount > 0 && (
          <button
            className={styles.ignoreAllBtn}
            onClick={handleIgnoreAll}
            disabled={bulkIgnoring}
          >
            {bulkIgnoring ? 'Ignoring…' : `Ignore All (${activeCount})`}
          </button>
        )}
      </div>

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
