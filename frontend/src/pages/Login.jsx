import { useState } from 'react'
import { useNavigate, useLocation, Link } from 'react-router-dom'
import { login as apiLogin } from '../api/auth'
import { useAuth } from '../context/AuthContext'
import styles from './Login.module.css'

export default function Login() {
  const navigate  = useNavigate()
  const location  = useLocation()
  const { login } = useAuth()

  const [username, setUsername] = useState('guest')
  const [password, setPassword] = useState('guest')
  const [error,    setError]    = useState(null)
  const [loading,  setLoading]  = useState(false)

  const from = location.state?.from?.pathname || '/my-cards'

  const handleSubmit = async e => {
    e.preventDefault()
    setError(null)
    setLoading(true)
    try {
      const res = await apiLogin(username, password)
      login(res.token, { username: res.username })
      navigate(from, { replace: true })
    } catch (err) {
      setError(err.message || 'Login failed')
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
            <span className={styles.subtitle}>Market Tracker</span>
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
              placeholder="admin"
              required
            />
          </div>

          <div className={styles.field}>
            <label className={styles.label}>Password</label>
            <input
              className={styles.input}
              type="password"
              autoComplete="current-password"
              value={password}
              onChange={e => setPassword(e.target.value)}
              placeholder="••••••••"
              required
            />
          </div>

          <button
            className={styles.submit}
            type="submit"
            disabled={loading || !username || !password}
          >
            {loading ? 'Signing in…' : 'Sign in'}
          </button>

          <p className={styles.guestHint}>
            No account? <Link to="/signup" style={{color:'var(--accent)'}}>Create one free</Link> — or sign in as guest above.
          </p>
        </form>
      </div>
    </div>
  )
}
