import { useState, useEffect, useCallback, useMemo } from 'react'
import {
  BarChart, Bar, XAxis, YAxis, Tooltip, ResponsiveContainer, Cell, CartesianGrid,
  LineChart, Line, ReferenceLine,
} from 'recharts'
import {
  getUsers, createUser, deleteUser, changePassword, changeRole,
  getPipelineHealth, getWorkflowStatus, getOutliers, toggleIgnore,
  getScrapeRuns, getScrapeRunsSummary,
} from '../api/admin'
import { useAuth } from '../context/AuthContext'
import pageStyles from './Page.module.css'
import styles from './Admin.module.css'

const TABS = ['Users', 'Pipeline', 'Runs', 'Outliers']

const WF_COLORS = ['#00d4aa', '#4a9eff', '#ff6b35', '#ffb332', '#a07ff0', '#e05555', '#3dba5e', '#ff9ff3']

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
      {tab === 'Runs'     && <RunsTab />}
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
      .then(([h, w]) => {
        setHealth(h)
        setWorkflows(w.workflows || [])
      })
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

/* ── Runs tab ──────────────────────────────────────────────────────────────── */
const ANOMALY_LABELS = {
  run_error:    'Run failed',
  zero_delta:   'Zero Δ — no new prices',
  low_hit_rate: 'Low hit rate (<10%)',
  high_errors:  'High error count',
}

function RunsTab() {
  const [runs,    setRuns]    = useState([])
  const [summary, setSummary] = useState(null)
  const [loading, setLoading] = useState(true)
  const [error,   setError]   = useState(null)
  const [wfFilter,    setWfFilter]    = useState('')
  const [sportFilter, setSportFilter] = useState('')

  useEffect(() => {
    setLoading(true)
    Promise.all([getScrapeRuns(200), getScrapeRunsSummary()])
      .then(([rd, sd]) => { setRuns(rd.runs || []); setSummary(sd) })
      .catch(e => setError(e.message))
      .finally(() => setLoading(false))
  }, [])

  const uniqueWorkflows = useMemo(() => [...new Set(runs.map(r => r.workflow))].sort(), [runs])
  const uniqueSports    = useMemo(() => [...new Set(runs.map(r => r.sport).filter(Boolean))].sort(), [runs])

  const wfColor = useMemo(() => {
    const m = {}
    uniqueWorkflows.forEach((w, i) => { m[w] = WF_COLORS[i % WF_COLORS.length] })
    return m
  }, [uniqueWorkflows])

  const filteredRuns = useMemo(() =>
    runs.filter(r =>
      (!wfFilter    || r.workflow === wfFilter) &&
      (!sportFilter || r.sport    === sportFilter)
    ), [runs, wfFilter, sportFilter]
  )

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
        {(wfFilter || sportFilter) && (
          <button className={styles.clearFilterBtn} onClick={() => { setWfFilter(''); setSportFilter('') }}>Clear</button>
        )}
        <span className={styles.runsCount}>{filteredRuns.length} runs</span>
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
              const dotClass = w.last_run_status === 'error' ? 'error'
                : (w.zero_delta_runs > 0 || w.success_rate < 75) ? 'warn'
                : 'healthy'
              const daysSince = w.last_run_at
                ? Math.floor((Date.now() - new Date(w.last_run_at)) / 86400000)
                : null
              return (
                <div
                  key={w.workflow}
                  className={`${styles.wfHealthCard} ${isSelected ? styles.wfHealthSelected : ''}`}
                  onClick={() => setWfFilter(isSelected ? '' : w.workflow)}
                >
                  <div className={styles.wfHealthHeader}>
                    <span className={`${styles.statusDot} ${styles['dot_' + dotClass]}`} />
                    <span className={styles.wfHealthName}>{w.workflow}</span>
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
                      {r.errors > 0 ? <span className={styles.textDanger}>{r.errors}</span> : r.errors}
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
