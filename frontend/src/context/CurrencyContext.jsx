import { createContext, useContext, useState, useEffect } from 'react'

const CurrencyContext = createContext(null)

const FALLBACK_RATE = 0.74   // CAD → USD fallback if fetch fails
const STORAGE_KEY   = 'currency_pref'

export function CurrencyProvider({ children }) {
  const [currency, setCurrency] = useState(
    () => localStorage.getItem(STORAGE_KEY) || 'CAD'
  )
  const [rate, setRate] = useState(FALLBACK_RATE)   // CAD → USD multiplier

  // Fetch live exchange rate once on mount
  useEffect(() => {
    fetch('https://api.exchangerate-api.com/v4/latest/CAD')
      .then(r => r.json())
      .then(data => {
        const usd = data?.rates?.USD
        if (usd && typeof usd === 'number') setRate(usd)
      })
      .catch(() => { /* use fallback */ })
  }, [])

  const toggle = () => {
    setCurrency(prev => {
      const next = prev === 'CAD' ? 'USD' : 'CAD'
      localStorage.setItem(STORAGE_KEY, next)
      return next
    })
  }

  /** Format a CAD dollar value in the currently selected currency. */
  const fmtPrice = (val, opts = {}) => {
    if (val == null || val === '' || val === 0) return opts.dash !== false ? '—' : '$0.00'
    const num = Number(val)
    if (isNaN(num)) return '—'
    const converted = currency === 'USD' ? num * rate : num
    return `$${converted.toLocaleString('en-CA', {
      minimumFractionDigits: 2,
      maximumFractionDigits: 2,
    })} ${currency}`
  }

  return (
    <CurrencyContext.Provider value={{ currency, rate, toggle, fmtPrice }}>
      {children}
    </CurrencyContext.Provider>
  )
}

export function useCurrency() {
  return useContext(CurrencyContext)
}
