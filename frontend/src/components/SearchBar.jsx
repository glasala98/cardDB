import { useState, useEffect, useRef } from 'react'
import { getSearchSuggestions } from '../api/search'
import styles from './SearchBar.module.css'

const GRADE_RE = /\b(PSA|BGS|SGC|CGC|HGA|CSG)\s*\d+(\.\d+)?\b/i

export default function SearchBar({ value, onChange, onSubmit, placeholder = 'Search cards…' }) {
  const [suggestions, setSuggestions] = useState([])
  const [open, setOpen] = useState(false)
  const [loading, setLoading] = useState(false)
  const debounceRef = useRef(null)
  const inputRef = useRef(null)
  const listRef = useRef(null)
  const detectedGrade = (value.match(GRADE_RE) || [])[0] ?? null

  useEffect(() => {
    clearTimeout(debounceRef.current)
    if (value.trim().length < 2) { setSuggestions([]); setOpen(false); return }
    debounceRef.current = setTimeout(async () => {
      setLoading(true)
      try {
        const res = await getSearchSuggestions(value.trim())
        setSuggestions(res ?? [])
        setOpen((res ?? []).length > 0)
      } catch { setSuggestions([]) }
      finally { setLoading(false) }
    }, 300)
    return () => clearTimeout(debounceRef.current)
  }, [value])

  function handleKey(e) {
    if (e.key === 'Enter') { setOpen(false); onSubmit?.(value) }
    if (e.key === 'Escape') { setOpen(false) }
  }

  function pick(s) {
    onChange(s.display_name)
    setOpen(false)
    onSubmit?.(s.display_name)
  }

  // Close on outside click
  useEffect(() => {
    function handler(e) {
      if (!inputRef.current?.contains(e.target) && !listRef.current?.contains(e.target))
        setOpen(false)
    }
    document.addEventListener('mousedown', handler)
    return () => document.removeEventListener('mousedown', handler)
  }, [])

  return (
    <div className={styles.wrap}>
      <div className={styles.inputRow}>
        <span className={styles.icon}>🔍</span>
        <input
          ref={inputRef}
          className={styles.input}
          type="text"
          value={value}
          onChange={e => onChange(e.target.value)}
          onKeyDown={handleKey}
          onFocus={() => suggestions.length && setOpen(true)}
          placeholder={placeholder}
          autoComplete="off"
          spellCheck={false}
        />
        {detectedGrade && (
          <span className={styles.gradePill}>{detectedGrade}</span>
        )}
        {loading && <span className={styles.spinner} />}
        {value && (
          <button className={styles.clear} onClick={() => { onChange(''); setSuggestions([]); setOpen(false); inputRef.current?.focus() }}>×</button>
        )}
      </div>
      {open && suggestions.length > 0 && (
        <ul ref={listRef} className={styles.dropdown}>
          {suggestions.map((s, i) => (
            <li key={i} className={styles.item} onMouseDown={() => pick(s)}>
              <span className={styles.name}>{s.display_name}</span>
              {s.year && <span className={styles.meta}>{s.year}</span>}
              {s.set_name && <span className={styles.meta}>{s.set_name}</span>}
            </li>
          ))}
        </ul>
      )}
    </div>
  )
}
