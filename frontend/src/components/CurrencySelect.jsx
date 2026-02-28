import { useCurrency } from '../context/CurrencyContext'
import styles from './CurrencySelect.module.css'

export default function CurrencySelect() {
  const { currency, toggle } = useCurrency()
  return (
    <select
      className={styles.select}
      value={currency}
      onChange={e => { if (e.target.value !== currency) toggle() }}
      title="Display currency"
    >
      <option value="CAD">CAD</option>
      <option value="USD">USD</option>
    </select>
  )
}
