import { useState } from 'react'
import { useNavigate, Link } from 'react-router-dom'
import { signup as apiSignup } from '../api/auth'
import { useAuth } from '../context/AuthContext'
import styles from './Login.module.css'

export default function Signup() {
  const navigate = useNavigate()
  const { login } = useAuth()

  const [username,    setUsername]    = useState('')
  const [displayName, setDisplayName] = useState('')
  const [password,    setPassword]    = useState('')
  const [confirm,     setConfirm]     = useState('')
  const [error,       setError]       = useState(null)
  const [loading,     setLoading]     = useState(false)

  const handleSubmit = async e => {
    e.preventDefault()
    setError(null)

    if (password !== confirm) {
      setError('Passwords do not match')
      return
    }

    setLoading(true)
    try {
      const res = await apiSignup(username, displayName, password)
      login(res.token, { username: res.username })
      navigate('/catalog', { replace: true })
    } catch (err) {
      setError(err.message || 'Could not create account')
    } finally {
      setLoading(false)
    }
  }

  return (
    <div className={styles.page}>
      <div className={styles.card}>
        <div className={styles.logo}>
          <div className={styles.logoMark}>
            <svg viewBox="0 0 18 18" fill="none" xmlns="http://www.w3.org/2000/svg" width="18" height="18">
              <rect x="1" y="3" width="11" height="14" rx="2" fill="currentColor" opacity="0.9"/>
              <rect x="6" y="1" width="11" height="14" rx="2" fill="currentColor" opacity="0.45"/>
            </svg>
          </div>
          <div className={styles.logoText}>
            <h1 className={styles.title}>CardDB</h1>
            <span className={styles.subtitle}>Create Account</span>
          </div>
        </div>

        <form className={styles.form} onSubmit={handleSubmit}>
          {error && <div className={styles.error}>{error}</div>}

          <div className={styles.field}>
            <label className={styles.label}>Username</label>
            <input
              className={styles.input}
              type="text"
              autoComplete="username"
              autoFocus
              value={username}
              onChange={e => setUsername(e.target.value)}
              placeholder="e.g. cardking99"
              required
            />
          </div>

          <div className={styles.field}>
            <label className={styles.label}>Display Name <span style={{fontWeight:400,textTransform:'none',letterSpacing:0}}>(optional)</span></label>
            <input
              className={styles.input}
              type="text"
              value={displayName}
              onChange={e => setDisplayName(e.target.value)}
              placeholder="Your name"
            />
          </div>

          <div className={styles.field}>
            <label className={styles.label}>Password</label>
            <input
              className={styles.input}
              type="password"
              autoComplete="new-password"
              value={password}
              onChange={e => setPassword(e.target.value)}
              placeholder="At least 6 characters"
              required
            />
          </div>

          <div className={styles.field}>
            <label className={styles.label}>Confirm Password</label>
            <input
              className={styles.input}
              type="password"
              autoComplete="new-password"
              value={confirm}
              onChange={e => setConfirm(e.target.value)}
              placeholder="••••••••"
              required
            />
          </div>

          <button
            className={styles.submit}
            type="submit"
            disabled={loading || !username || !password || !confirm}
          >
            {loading ? 'Creating account…' : 'Create account'}
          </button>

          <p className={styles.guestHint}>
            Already have an account? <Link to="/login" style={{color:'var(--accent)'}}>Sign in</Link>
          </p>
        </form>
      </div>
    </div>
  )
}
