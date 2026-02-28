# CardDB Frontend

React 18 + Vite app. All `/api` requests proxy to the FastAPI backend.

## Start

```bash
npm install
npm run dev      # dev server at http://localhost:5173
npm run build    # production build → dist/
npm run preview  # preview production build locally
```

## Port / Proxy

| Environment | Frontend | API target |
|-------------|----------|-----------|
| Local dev | :5173 | http://localhost:8001 |
| Production | nginx serves `dist/` | nginx proxies `/api/` → :8000 |

The proxy is configured in [vite.config.js](vite.config.js).

---

## Pages

| Route | Component | Description |
|-------|-----------|-------------|
| `/login` | `Login.jsx` | Username + password form. Stores JWT in localStorage. |
| `/ledger` | `CardLedger.jsx` | Main card table with search, filters, inline cost-basis edit, add/scan/bulk-import, rescrape, export CSV, card-of-the-day widget. |
| `/ledger/:cardName` | `CardInspect.jsx` | Single card detail: price history chart, raw eBay sales, grading ROI calculator, card flip image viewer, not-found price override. |
| `/portfolio` | `Portfolio.jsx` | Portfolio stats strip, value chart over time, trend breakdown, top 10 cards, top gainers/losers. |
| `/master-db` | `MasterDB.jsx` | Young Guns market DB table + 9 analytics sections (Market Overview, Price Analysis, Grading, Player Compare, Correlation, Value Finder, Rookie Impact Score, Team Premium, Position). |
| `/nhl-stats` | `NHLStats.jsx` | Sortable NHL player stats table with card values, position/team filters. |
| `/charts` | `Charts.jsx` | Recharts visualizations: value distribution, trend breakdown, grade mix, top sets, cost vs value scatter. |
| `/archive` | `Archive.jsx` | Soft-deleted cards. Restore to active collection. |
| `/admin` | `Admin.jsx` | User list, add user, delete user, change password. Visible only to `admin` role. |

---

## Components

| Component | Purpose |
|-----------|---------|
| `Navbar.jsx` | Sidebar navigation, logout, help modal, public mode badge, share link |
| `ProtectedRoute.jsx` | Redirects to `/login` if not authenticated |
| `AddCardModal.jsx` | Modal to add a single card manually |
| `ScanCardModal.jsx` | Upload card images → Claude Vision scan → pre-filled add form |
| `BulkUploadModal.jsx` | Upload CSV → bulk import endpoint |
| `EditCardModal.jsx` | Edit card fields (value, cost basis, purchase date, tags) |
| `ConfidenceBadge.jsx` | Colored badge: `high` / `medium` / `low` / `estimated` / `not found` / `none` / `unknown` |
| `TrendBadge.jsx` | Colored badge: `up` / `stable` / `down` / `no data` |
| `PriceChart.jsx` | Recharts line chart for price history |
| `CardTable.jsx` | Reusable table shell with sortable column headers |
| `CurrencySelect.jsx` | CAD / USD toggle dropdown |
| `ConfirmDialog.jsx` | Generic confirmation modal (archive, delete) |
| `HelpModal.jsx` | Help / feature guide modal (opened from navbar) |
| `ScrapeProgressModal.jsx` | Polls `/api/stats/scrape-status` every 15s, shows GitHub Actions run progress |

---

## Context Providers

All three wrap the entire app in `App.jsx`.

| Provider | Hook | Purpose |
|----------|------|---------|
| `AuthProvider` | `useAuth()` | JWT storage in localStorage, user info (`username`, `display_name`, `role`), axios interceptor for Bearer header |
| `CurrencyProvider` | `useCurrency()` | CAD/USD toggle, live exchange rate fetch, `fmtPrice(value)` helper |
| `PublicModeProvider` | `usePublicMode()` | Detects `?public=true` URL param — hides write actions (read-only share link) |

---

## API Clients (`src/api/`)

Each file wraps one area of the FastAPI backend. The shared axios instance in `client.js` auto-unwraps `res.data` — so all functions return the data directly (not the axios response object).

| File | Wraps |
|------|-------|
| `client.js` | Axios instance, base URL `/api`, 30s timeout, data-unwrap interceptor |
| `auth.js` | `login()`, `getMe()`, `logout()` |
| `cards.js` | `getCards()`, `addCard()`, `updateCard()`, `archiveCard()`, `restoreCard()`, `scrapeCard()`, `getCardDetail()`, `fetchImage()`, `getCardOfTheDay()`, `bulkImport()`, `getPortfolioHistory()`, `getArchive()` |
| `masterDb.js` | `getYoungGuns()`, `getMarketMovers()`, `getPriceHistory()`, `getPortfolioHistory()`, `getNhlStats()`, `getSeasonalTrends()`, `getGradingLookup()`, `scrapeYgCard()`, `updateOwnership()` |
| `stats.js` | `getAlerts()`, `triggerScrape()`, `getScrapeStatus()` |
| `admin.js` | `listUsers()`, `createUser()`, `deleteUser()`, `changePassword()` |
| `scan.js` | `analyzeCard(frontFile, backFile)` |

---

## CSS Modules

Every component has a scoped `.module.css` file (e.g., `CardLedger.module.css`). Import and use like:

```jsx
import styles from './CardLedger.module.css'
// ...
<div className={styles.topBar}>
```

Global CSS variables (colors, spacing, shadows) are defined in `src/index.css`.

---

## Public / Share Mode

Append `?public=true` to any URL to enter read-only public mode. This bypasses the login requirement and hides all write actions (add, edit, scrape, archive, etc.). Useful for sharing a portfolio view.

`usePublicMode()` returns `{ isPublic: boolean }`.
