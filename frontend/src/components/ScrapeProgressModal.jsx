import { useState, useEffect, useRef } from 'react'
import { getScrapeStatus } from '../api/stats'
import styles from './ScrapeProgressModal.module.css'

const POLL_INTERVAL = 15000   // 15 s

function timeAgo(isoStr) {
  if (!isoStr) return null
  const secs = Math.floor((Date.now() - new Date(isoStr).getTime()) / 1000)
  if (secs < 60)  return `${secs}s ago`
  if (secs < 3600) return `${Math.floor(secs / 60)}m ago`
  return `${Math.floor(secs / 3600)}h ago`
}

function elapsed(isoStr) {
  if (!isoStr) return 0
  return Math.floor((Date.now() - new Date(isoStr).getTime()) / 1000)
}

function fmtElapsed(secs) {
  if (secs < 60) return `${secs}s`
  return `${Math.floor(secs / 60)}m ${secs % 60}s`
}

const STATUS_LABEL = {
  queued:      { label: 'Queued',      color: '#9aa0b4' },
  in_progress: { label: 'Running',     color: '#4f8ef7' },
  completed:   { label: 'Completed',   color: '#4caf82' },
  no_runs:     { label: 'No runs yet', color: '#9aa0b4' },
}

const CONCLUSION_LABEL = {
  success:   { label: 'Success',   color: '#4caf82' },
  failure:   { label: 'Failed',    color: '#e05c5c' },
  cancelled: { label: 'Cancelled', color: '#9aa0b4' },
}

const STEP_ICON = {
  completed:   { success: '✓', failure: '✗', cancelled: '–' },
  in_progress: '●',
  queued:      '○',
}

function stepIcon(step) {
  if (step.status === 'completed') return STEP_ICON.completed[step.conclusion] ?? '✓'
  if (step.status === 'in_progress') return STEP_ICON.in_progress
  return STEP_ICON.queued
}

function stepClass(step, styles) {
  if (step.status === 'completed' && step.conclusion === 'success')   return styles.stepDone
  if (step.status === 'completed' && step.conclusion === 'failure')   return styles.stepFailed
  if (step.status === 'in_progress') return styles.stepRunning
  return styles.stepQueued
}

export default function ScrapeProgressModal({ estimatedMins, onClose }) {
  const [run,     setRun]     = useState(null)
  const [error,   setError]   = useState(null)
  const [tick,    setTick]    = useState(0)   // forces re-render every second for elapsed timer
  const intervalRef = useRef(null)
  const tickRef     = useRef(null)

  const poll = () => {
    getScrapeStatus()
      .then(d => { setRun(d); setError(null) })
      .catch(e => setError(e.message))
  }

  useEffect(() => {
    poll()
    intervalRef.current = setInterval(poll, POLL_INTERVAL)
    tickRef.current     = setInterval(() => setTick(t => t + 1), 1000)
    return () => {
      clearInterval(intervalRef.current)
      clearInterval(tickRef.current)
    }
  }, [])

  const estimatedSecs = (estimatedMins ?? 30) * 60
  const elapsedSecs   = run?.started_at ? elapsed(run.started_at) : 0
  const pct = run?.status === 'completed'
    ? 100
    : Math.min(95, Math.round((elapsedSecs / estimatedSecs) * 100))

  const statusInfo = run
    ? (run.status === 'completed'
        ? CONCLUSION_LABEL[run.conclusion] ?? STATUS_LABEL.completed
        : STATUS_LABEL[run.status] ?? STATUS_LABEL.queued)
    : STATUS_LABEL.queued

  const isDone = run?.status === 'completed'

  return (
    <div className={styles.overlay} onClick={e => e.target === e.currentTarget && onClose()}>
      <div className={styles.modal}>

        <div className={styles.header}>
          <h2 className={styles.title}>⟳ Rescrape Progress</h2>
          <button className={styles.closeBtn} onClick={onClose}>✕</button>
        </div>

        <div className={styles.body}>
          {error && <p className={styles.error}>{error}</p>}

          {run && (
            <>
              <div className={styles.statusRow}>
                <span className={styles.statusDot} style={{ color: statusInfo.color }}>●</span>
                <span className={styles.statusLabel} style={{ color: statusInfo.color }}>
                  {statusInfo.label}
                </span>
                {run.run_number && (
                  <span className={styles.runNum}>Run #{run.run_number}</span>
                )}
                {run.started_at && (
                  <span className={styles.startedAt}>started {timeAgo(run.started_at)}</span>
                )}
              </div>

              {/* Progress bar */}
              <div className={styles.barWrap}>
                <div
                  className={`${styles.bar} ${isDone ? styles.barDone : styles.barActive}`}
                  style={{ width: `${pct}%` }}
                />
              </div>
              <div className={styles.barMeta}>
                <span>{pct}%</span>
                {!isDone && run.started_at && (
                  <span>Elapsed: {fmtElapsed(elapsedSecs)} / ~{estimatedMins}m estimated</span>
                )}
                {isDone && <span>Completed in {fmtElapsed(elapsedSecs)}</span>}
              </div>

              {/* Step log */}
              {run.steps?.length > 0 && (
                <div className={styles.log}>
                  <p className={styles.logTitle}>Job steps</p>
                  {run.steps.map((s, i) => (
                    <div key={i} className={`${styles.step} ${stepClass(s, styles)}`}>
                      <span className={styles.stepIcon}>{stepIcon(s)}</span>
                      <span className={styles.stepName}>{s.name}</span>
                      {s.started_at && (
                        <span className={styles.stepTime}>{timeAgo(s.started_at)}</span>
                      )}
                    </div>
                  ))}
                </div>
              )}

              <p className={styles.note}>
                Scrape runs on GitHub Actions — closing this won't stop it.
              </p>

              <div className={styles.actions}>
                {run.html_url && (
                  <a
                    href={run.html_url}
                    target="_blank"
                    rel="noopener noreferrer"
                    className={styles.ghLink}
                  >
                    View full log on GitHub ↗
                  </a>
                )}
                <button className={styles.closeAction} onClick={onClose}>
                  {isDone ? 'Close & Refresh' : 'Close'}
                </button>
              </div>
            </>
          )}

          {!run && !error && (
            <p className={styles.waiting}>Waiting for GitHub Actions to start…</p>
          )}
        </div>

      </div>
    </div>
  )
}
