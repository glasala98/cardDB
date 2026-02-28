import {
  LineChart, Line, XAxis, YAxis, CartesianGrid,
  Tooltip, ResponsiveContainer
} from 'recharts'
import styles from './PriceChart.module.css'

/**
 * Line chart for price history.
 * Props:
 *   data: [{ date: 'YYYY-MM-DD', price: number }]
 *   title?: string
 */
export default function PriceChart({ data, title }) {
  if (!data || data.length === 0) {
    return <div className={styles.empty}>No price history available.</div>
  }

  return (
    <div className={styles.wrapper}>
      {title && <h3 className={styles.title}>{title}</h3>}
      <ResponsiveContainer width="100%" height={220}>
        <LineChart data={data} margin={{ top: 8, right: 16, left: 0, bottom: 0 }}>
          <CartesianGrid strokeDasharray="3 3" stroke="var(--border)" />
          <XAxis
            dataKey="date"
            tick={{ fill: 'var(--text-secondary)', fontSize: 11 }}
            tickLine={false}
            axisLine={{ stroke: 'var(--border)' }}
          />
          <YAxis
            tick={{ fill: 'var(--text-secondary)', fontSize: 11 }}
            tickLine={false}
            axisLine={false}
            tickFormatter={v => `$${v}`}
          />
          <Tooltip
            contentStyle={{
              background: 'var(--bg-card)',
              border: '1px solid var(--border)',
              borderRadius: 8,
              color: 'var(--text-primary)',
              fontSize: 12,
            }}
            formatter={v => [`$${Number(v).toFixed(2)}`, 'Fair Value']}
          />
          <Line
            type="monotone"
            dataKey="price"
            stroke="var(--accent)"
            strokeWidth={2}
            dot={false}
            activeDot={{ r: 4, fill: 'var(--accent)' }}
          />
        </LineChart>
      </ResponsiveContainer>
    </div>
  )
}
