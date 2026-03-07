import styles from './HelpModal.module.css'

const SECTIONS = [
  {
    icon: '🗂️',
    title: 'Card Catalog',
    items: [
      'Public market database — no login required to browse',
      'Search across all cards by player name, set, year, or sport',
      'Filter by sport (NHL/NBA/NFL/MLB), year, and set name',
      'Tier badges: Staple (teal), Premium (amber), Stars (purple) mark high-value cards',
      'RC badge marks confirmed rookie cards',
      'Click any row to open a detail panel with price summary and sparkline chart',
      'Add a card directly to your collection from the detail panel',
      'Share a read-only link to the catalog using the share icon in the nav',
    ],
  },
  {
    icon: '🆕',
    title: 'New Releases',
    items: [
      'Browse recently released card sets grouped by sport and season',
      'Filter by sport tab (NHL/NBA/NFL/MLB) and season range',
      'Each set card shows top cards by value, average price, and coverage percentage',
      'Momentum badge (+/-%) shows price trend vs. previous scrape',
      'Click a set to jump to that set in the full catalog',
    ],
  },
  {
    icon: '⭐',
    title: 'My Collection',
    items: [
      'Your personal subset of the catalog — cards you have marked as owned',
      'Add cards from the Catalog detail panel or Card Ledger',
      'Track grade (raw, PSA, BGS), quantity, and cost basis per card',
    ],
  },
  {
    icon: '📋',
    title: 'Card Ledger',
    items: [
      'Full view of your collection with live market prices and P&L',
      'Click any row to open the Card Inspect detail view',
      'Filter sidebar: search, sport, grade, year, set, price range, trend, confidence',
      'On mobile: tap the Filters button to open the filter drawer',
      'Sort by any column — player, value, gain/loss, last scraped, etc.',
      'Add cards with + Add Card, import via CSV, or scan with 📷 Scan Card (AI)',
      'Export your full ledger as CSV',
      'Archive cards you no longer own (they can be restored from the Archive tab)',
    ],
  },
  {
    icon: '🔍',
    title: 'Card Inspect',
    items: [
      'Full card detail: fair value, cost basis, unrealized gain/loss, min/max, sales count',
      'Price history sparkline chart — track value over time',
      'eBay sales history table with links to individual listings',
      'Grading ROI Calculator — enter grading and shipping costs to see if grading pays off',
      'Manual price override for cards eBay cannot find',
      'Rescrape button to refresh eBay data on demand',
      'Click the card image to open a lightbox with front/back flip',
    ],
  },
  {
    icon: '📈',
    title: 'Portfolio',
    items: [
      'Total collection value, cost basis, unrealized P&L, and card count',
      'Portfolio value chart — historical snapshots of your collection over time',
      'Trend breakdown: how many cards are up, stable, or down',
      'Top 10 most valuable cards in your collection',
      'Top Gainers and Top Losers by dollar change',
    ],
  },
  {
    icon: '📊',
    title: 'Charts',
    items: [
      'Value Distribution — cards by price tier',
      'Trend Breakdown — up/stable/down split',
      'Grade Distribution — PSA 10, other grades, raw breakdown',
      'Cards by Set — which sets dominate your collection',
      'Cost vs. Value — compare what you paid vs. current market for top cards',
    ],
  },
  {
    icon: '🗃️',
    title: 'Archive',
    items: [
      'View all cards you have archived (soft-removed from your active ledger)',
      'Search archived cards by name',
      'Restore any card back to your active collection with one click',
    ],
  },
  {
    icon: '⚙️',
    title: 'Settings',
    items: [
      'Toggle between CAD and USD — conversion uses a live exchange rate',
      'Compact density mode reduces row padding for more cards on screen',
      'All prices are stored in CAD internally; USD is a display conversion',
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
