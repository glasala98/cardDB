import { Navigate, useLocation } from 'react-router-dom'
import { useAuth } from '../context/AuthContext'

export default function ProtectedRoute({ children }) {
  const { user, loading } = useAuth()
  const location = useLocation()

  // Allow ?public=true URLs to bypass login (read-only sharing)
  const isPublic = new URLSearchParams(location.search).get('public') === 'true'
  if (isPublic) return children

  if (loading) return null   // wait for token check before redirecting

  if (!user) {
    return <Navigate to="/login" state={{ from: location }} replace />
  }

  return children
}
