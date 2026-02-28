import styles from './HelpModal.module.css'

const SECTIONS = [
  {
    icon: '📋',
    title: 'Card Ledger',
    items: [
      'Browse and manage your personal card collection',
      'Click any row to open the full Card Inspect view with price history',
      'Use the search bar to find cards by name, player, set or year',
      'Filter by Trend, Grade, Set, Year, Tag or Confidence level',
      'Click column headers to sort by any field',
      'Export your collection as a CSV file with the ↓ Export button',
      'Bulk import cards with the ↑ Bulk Import button (CSV with Card Name column)',
      'Scan a card photo with 📷 Scan Card — AI identifies the card and pre-fills the add form',
      'Add new cards manually with the + Add Card button',
    ],
  },
  {
    icon: '🔍',
    title: 'Card Inspect',
    items: [
      'Full card detail: fair value, cost basis, gain/loss, min/max, sales count',
      'Price history chart — track how the card value has changed over time',
      'eBay sales history table with listing links',
      'Grading ROI Calculator — enter grading + shipping costs to see if grading is profitable',
      'Not-Found price override — manually set a price for cards eBay can\'t find',
      'Rescrape button to refresh the card\'s eBay data on demand',
    ],
  },
  {
    icon: '📈',
    title: 'Portfolio',
    items: [
      'Collection summary: total value, cost, unrealized P&L, card count',
      'Portfolio value chart shows historical value snapshots over time',
      'Trend breakdown bar chart — how many cards are up/stable/down',
      'Top 10 Most Valuable cards in your collection',
      'Top Gainers and Top Losers by dollar gain/loss',
      'Card of the Day — a daily highlighted card from your collection',
    ],
  },
  {
    icon: '🏒',
    title: 'Young Guns Master DB',
    items: [
      '500+ Young Guns cards with daily-updated eBay prices',
      'Price Mode selector: view Raw, PSA 8/9/10, or BGS 9/9.5/10 prices',
      'Filter by Season, Team, or "My Cards" to see only cards you own',
      'Market Movers banner shows biggest recent gainers and losers',
      'Analytics panel with Market Overview, Price Analysis, Grading Analytics, Player Compare',
      'Correlation Analytics: points vs value scatter, team premiums, position breakdown, nationality, draft position',
      'Seasonal Trends: average YG card prices by month',
    ],
  },
  {
    icon: '📊',
    title: 'Charts',
    items: [
      'Value Distribution — how many cards are in each price tier',
      'Trend Breakdown pie chart',
      'Grade Distribution — PSA 10, raw, ungraded breakdown',
      'Cards by Set — top sets in your collection',
      'Cost vs Current Value comparison for your top gainers',
    ],
  },
  {
    icon: '🗃️',
    title: 'Archive',
    items: [
      'View all archived (soft-deleted) cards',
      'Search archived cards by name',
      'Restore any card back to your active collection',
    ],
  },
  {
    icon: '💰',
    title: 'Currency Toggle',
    items: [
      'Switch between CAD and USD using the currency selector in any page header',
      'USD conversion uses a live exchange rate fetched at app load',
      'All prices are stored in CAD internally',
    ],
  },
]

export default function HelpModal({ onClose }) {
  return (
    <div className={styles.overlay} onClick={e => e.target === e.currentTarget && onClose()}>
      <div className={styles.modal}>
        <div className={styles.header}>
          <h2 className={styles.title}>Site Guide</h2>
          <button className={styles.closeBtn} onClick={onClose}>✕</button>
        </div>
        <div className={styles.body}>
          {SECTIONS.map(s => (
            <div key={s.title} className={styles.section}>
              <div className={styles.sectionTitle}>
                <span className={styles.sectionIcon}>{s.icon}</span>
                {s.title}
              </div>
              <ul className={styles.list}>
                {s.items.map((item, i) => <li key={i}>{item}</li>)}
              </ul>
            </div>
          ))}
        </div>
      </div>
    </div>
  )
}
