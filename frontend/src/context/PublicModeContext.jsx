import { createContext, useContext } from 'react'
import { useSearchParams } from 'react-router-dom'

const PublicModeContext = createContext(false)

export function PublicModeProvider({ children }) {
  const [params] = useSearchParams()
  const isPublic = params.get('public') === 'true'
  return (
    <PublicModeContext.Provider value={isPublic}>
      {children}
    </PublicModeContext.Provider>
  )
}

export const usePublicMode = () => useContext(PublicModeContext)
