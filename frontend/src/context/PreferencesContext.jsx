import { createContext, useContext, useEffect, useState } from 'react'

const PreferencesContext = createContext(null)

const STORAGE_KEY = 'carddb_prefs'

function load() {
  try { return JSON.parse(localStorage.getItem(STORAGE_KEY)) || {} } catch { return {} }
}
function save(prefs) {
  localStorage.setItem(STORAGE_KEY, JSON.stringify(prefs))
}

export function PreferencesProvider({ children }) {
  const stored = load()
  const [density, setDensityState] = useState(stored.density || 'comfortable')

  const setDensity = (value) => {
    setDensityState(value)
    save({ ...load(), density: value })
  }

  // Apply compact class to body whenever density changes
  useEffect(() => {
    document.body.classList.toggle('compact', density === 'compact')
  }, [density])

  return (
    <PreferencesContext.Provider value={{ density, setDensity }}>
      {children}
    </PreferencesContext.Provider>
  )
}

export function usePreferences() {
  return useContext(PreferencesContext)
}
