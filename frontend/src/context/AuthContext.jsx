import { createContext, useContext, useState, useEffect, useCallback } from 'react'
import client from '../api/client'
import { getMe, logout as apiLogout } from '../api/auth'

const AuthContext = createContext(null)

const TOKEN_KEY = 'auth_token'

export function AuthProvider({ children }) {
  const [user,    setUser]    = useState(null)   // { username, display_name, role }
  const [loading, setLoading] = useState(true)   // true while checking stored token

  // On mount: if we have a stored token, verify it with /auth/me
  useEffect(() => {
    const token = localStorage.getItem(TOKEN_KEY)
    if (!token) {
      setLoading(false)
      return
    }
    client.defaults.headers.common['Authorization'] = `Bearer ${token}`
    getMe()
      .then(data => setUser(data))
      .catch(() => {
        // Token expired or invalid — clear it
        localStorage.removeItem(TOKEN_KEY)
        delete client.defaults.headers.common['Authorization']
      })
      .finally(() => setLoading(false))
  }, [])

  const login = useCallback((token, userData) => {
    localStorage.setItem(TOKEN_KEY, token)
    client.defaults.headers.common['Authorization'] = `Bearer ${token}`
    setUser(userData)
    // Fetch full profile (role, display_name) immediately after login
    getMe().then(data => setUser(data)).catch(() => {})
  }, [])

  const logout = useCallback(async () => {
    try { await apiLogout() } catch (_) { /* ignore */ }
    localStorage.removeItem(TOKEN_KEY)
    delete client.defaults.headers.common['Authorization']
    setUser(null)
  }, [])

  return (
    <AuthContext.Provider value={{ user, loading, login, logout }}>
      {children}
    </AuthContext.Provider>
  )
}

export function useAuth() {
  return useContext(AuthContext)
}

/** Returns true when the logged-in user has the 'guest' role. */
export function useIsGuest() {
  const { user } = useContext(AuthContext)
  return user?.role === 'guest'
}

/** Returns true when the logged-in user has the 'admin' role. */
export function useIsAdmin() {
  const { user } = useContext(AuthContext)
  return user?.role === 'admin'
}
