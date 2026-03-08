# CardDB — Frontend Reference

React 18 + Vite. CSS Modules for scoped styles. Built to `frontend/dist/` and served by FastAPI in production.

---

## App Shell — `App.jsx`

Context providers (outermost to innermost):
```
BrowserRouter
  AuthProvider         ← JWT token, current user, role
  PreferencesProvider  ← density (comfortable/compact), persisted in localStorage
  CurrencyProvider     ← CAD/USD toggle, live exchange rate
    PublicModeProvider ← ?public=true read-only share mode
      Routes
```

Public routes (no auth): `/login`, `/signup`, `/catalog`
Protected routes: everything else — wrapped in `<ProtectedRoute>` which redirects to `/login` if no valid token.

Default route: `/` → redirect to `/catalog`.

---

## Pages

### `/catalog` — Card Catalog (`Catalog.jsx`)

Browse all 1.26M+ cards in the reference database.

**Features:**
- Search, sport filter (NHL/NBA/NFL/MLB), year, set name, rookie flag
- Sort by player/year/fair_value/num_sales
- 50 cards per page, paginated
- Right-side slide-in panel (`CatalogCardDetail.jsx`) on row click — shows price, trend, sparkline, tier badge
- Add to collection button (auth required) / "Sign in to add" (guest/public)
- Owned cards show a ✓ badge (from `GET /api/collection/owned-ids`)
- Tier badges: Staple / Premium / Stars

**State:** search query, sport, year, set, page, sort/dir, owned IDs set, open panel card.

---

### `/collection` — My Collection (`Collection.jsx`)

The user's catalog-linked ownership record.

**Features:**
- Cards joined with catalog + market prices
- Columns: player, set, year, grade, qty, cost basis, market value, gain/loss
- Add from catalog (via Catalog page → Add button)
- Edit grade/qty/cost/notes inline
- Delete row

**What it is NOT:** this is not the ledger (legacy personal cards). It's the catalog-FK system.

---

### `/ledger` — Card Ledger (`CardLedger.jsx`)

The user's personal card list — text-keyed, predates the catalog system.

**Features:**
- All user's cards with fair value, cost basis, gain/loss, confidence badge, trend badge
- Rescrape individual card (triggers background scrape via API)
- Edit card (fair value override, cost basis, purchase date, tags)
- Archive card (soft delete with restore)
- Bulk import via CSV upload
- Scan card via camera/image upload (→ Claude Vision → pre-fills add form)
- Rescrape All button — dispatches GitHub Actions workflow, opens `ScrapeProgressModal`

**State:** cards list, loading, scraping states, active modals.

---

### `/ledger/:cardName` — Card Inspect (`CardInspect.jsx`)

Detailed view for a single ledger card.

**Layout:** Side-by-side — card image (200×280) left, title + metrics right.

**Features:**
- Price history chart (sparkline via `PriceChart`)
- Confidence badge + tier badge (GOLD/SILVER/BRONZE by value)
- eBay sold listings table with dates and prices
- eBay search link
- Manual "Fetch image" button (Selenium — only shown if listing URLs exist)
- Lightbox on image click — 3D front/back flip if back image available
- Manual price override form (shown for "not found" cards)
- Grading ROI Calculator table:
  - Raw baseline
  - PSA 9, PSA 10 (if data available)
  - BGS 9.5, BGS 10 (if data available)
  - TAG (fee shown, no market data)
  - Green/red ROI highlighting
  - Data sourced from: master DB CSV → market_prices.graded_data → rookie_price_history

---

### `/portfolio` — Portfolio Overview (`Portfolio.jsx`)

Personal portfolio analytics.

**Features:**
- Total value, total cards, average value, total gain/loss
- Portfolio value over time chart
- Top 10 cards by value
- Best gainers / worst losers
- "Card of the Day" highlight

---

### `/charts` — Charts (`Charts.jsx`)

Data visualization for the ledger.

**Charts:**
- Value distribution (histogram)
- Price trend over time
- Grade distribution
- Sets breakdown (by count / value)
- Cost vs fair value scatter

---

### `/archive` — Archive (`Archive.jsx`)

Soft-deleted ledger cards. Restore button returns card to active ledger.

---

### `/settings` — Settings (`Settings.jsx`)

**All users:** Currency toggle (CAD/USD), display density (comfortable/compact).

---

### `/admin` — Admin Dashboard (`Admin.jsx`)

Full scrape monitoring and data management. Admin role required. Five tabs:

**Pipeline tab**
- Coverage stats: total priced, priced in last 7d / 30d
- Workflow health cards for all 9 tracked workflows — status dot, last run time, consecutive-failure badge (red `✕N`), overdue badge (amber) if older than expected cadence
- ▶ Run trigger button per workflow (dispatches `workflow_dispatch` via GitHub API)

**Runs tab**
- Active jobs: live progress bars (`cards_processed / cards_total`), hit rate (`cards_found / cards_processed`), throughput (cards/hr), ETA
- Completed run history: status, hit rate, delta count, anomaly flags (`timed_out`, `zero_delta`, `low_hit_rate`, `high_errors`)

**Quality tab**
- Snapshot audit: missing prices, stale data, catalog coverage gaps

**Sealed tab**
- Browse/edit all `sealed_products` rows (MSRP, box price, pack config)
- Data quality panel: sport mismatches, bad MSRP ($1.00 parse errors), duplicate rows
- One-click "Fix mismatches" button → `DELETE /api/admin/sealed-products/mismatches`

**Outliers tab**
- Review cards with statistically anomalous prices
- Bulk-ignore selected outliers

**Users tab**
- Add/delete users, change passwords, assign roles

---

### `/master-db` — Young Guns Market DB (`MasterDB.jsx`)

Legacy analytics page for the YG/Rookie market CSV database. Accessible by URL but not in sidebar navigation.

**Sections:**
1. Overview table with PSA/BGS prices
2. Rookie cards owned / not owned filter
3. Grade comparison (PSA 9 vs PSA 10 premiums)
4. Price history charts per player
5. Portfolio tracking
6. Player bios / NHL stats integration
7. Standings
8. Correlation analytics (price vs performance R²)
9. Raw sales viewer

---

### `/nhl-stats` — NHL Stats (`NHLStats.jsx`)

NHL player stats cross-referenced with card values. Not in sidebar, accessible by URL.

---

---

## Components

### `Navbar.jsx`
- Desktop: vertical sidebar (left) — Card Catalog · Card Ledger · Portfolio + settings gear
- Mobile: fixed bottom tab bar — Catalog · Ledger · Portfolio · Settings
- Shows logged-in username and logout button

### `PageTabs.jsx`
Shared tab bar for page-group navigation:
- `/catalog` ↔ `/collection` (Browse | My Collection)
- `/ledger` ↔ `/archive` (Active | Archive)
- `/portfolio` ↔ `/charts` (Overview | Charts)

### `CardTable.jsx`
Reusable sortable table for card lists. Handles click-to-sort column headers, loading states, empty states.

### `PriceChart.jsx`
SVG sparkline / line chart for price history. Used on CardInspect and MasterDB pages.

### `ConfidenceBadge.jsx`
Color-coded badge for scrape confidence level:
- ✅ High — exact parallel + serial match
- 🟡 Medium — parallel dropped, set + serial match
- 🟠 Low — broad match (player + card# + serial)
- 🔴 Estimated — serial-extrapolated price
- ⬜ No data / Unknown

### `TrendBadge.jsx`
Displays price trend direction: ↑ up (green), ↓ down (red), → stable (gray).

### `CatalogCardDetail.jsx`
Slide-in panel from the right on Catalog page row click. Shows:
- Card name, tier badge
- Fair value, trend badge, confidence badge
- Price sparkline
- Num sales, min, max
- Add to Collection button / ✓ Owned badge / Sign in to add

### `ScrapeProgressModal.jsx`
Modal that polls `GET /api/stats/scrape-status` every 15s while a GitHub Actions workflow is running. Shows step log and status.

### `AddCardModal.jsx` / `EditCardModal.jsx`
Modal forms for adding and editing ledger cards.

### `BulkUploadModal.jsx`
CSV drag-and-drop upload → bulk card import.

### `ScanCardModal.jsx`
Camera/file upload → Claude Vision → pre-fills card name + fields.

### `ProtectedRoute.jsx`
Redirects to `/login` if `AuthContext` has no valid token. Wraps all authenticated pages in `App.jsx`.

### `ConfirmDialog.jsx`
Generic "Are you sure?" modal for destructive actions.

### `HelpModal.jsx`
Keyboard shortcut and usage guide overlay.

---

## Contexts

### `AuthContext.jsx`
- `user`: `{username, display_name, role}` or null
- `login(username, password)`: POST /api/auth/login → store JWT in localStorage
- `logout()`: clear localStorage → redirect /login
- `isAdmin`: shorthand `user?.role === 'admin'`
- On mount: reads token from localStorage, calls `/api/auth/me` to validate

### `CurrencyContext.jsx`
- `currency`: `'CAD'` or `'USD'`, persisted in localStorage
- `toggle()`: switch between CAD and USD
- `fmtPrice(v)`: converts CAD value to display currency using live exchange rate (fetched once per session from a public FX API)
- `rate`: current CAD→USD rate

### `PreferencesContext.jsx`
- `density`: `'comfortable'` or `'compact'`, persisted in localStorage
- Applies `body.compact` class when compact — tighter padding/font across all tables

### `PublicModeContext.jsx`
- `isPublic`: true when `?public=true` in URL
- Public mode: Catalog is viewable, all write actions disabled, no auth required

---

## API Layer — `src/api/`

All files use `client.js` — an axios instance with base URL `/api` and a response interceptor that auto-unwraps `response.data`. Never call `.data` on results.

| File | Exports |
|---|---|
| `auth.js` | `login()`, `me()`, `logout()` |
| `cards.js` | `getCards()`, `getCardDetail()`, `addCard()`, `updateCard()`, `deleteCard()`, `archiveCard()`, `restoreCard()`, `scrapeCard()`, `fetchImage()`, `bulkImport()` |
| `catalog.js` | `browseCatalog()`, `getCatalogFilters()` |
| `collection.js` | `getCollection()`, `getOwnedIds()`, `addToCollection()`, `updateCollection()`, `removeFromCollection()` |
| `masterDb.js` | `getMasterDb()`, `getGradingLookup()`, `getPriceHistory()`, `getPortfolioHistory()`, `getRawSales()`, `scrapeYGCard()` |
| `stats.js` | `triggerScrape()`, `getScrapeStatus()`, `getWorkflowStatus()` |
| `admin.js` | `getUsers()`, `createUser()`, `deleteUser()`, `changePassword()`, `getScrapeRuns()`, `getScrapeRunsSummary()`, `getScrapeRunErrors()`, `getDataQuality()`, `getSnapshotAudit()`, `getPipelineHealth()`, `getSealedProductsAdmin()`, `updateSealedProduct()`, `getSealedQuality()`, `deleteSealedMismatches()`, `triggerWorkflow()`, `getOutliers()`, `bulkIgnoreOutliers()` |
| `scan.js` | `analyzeCard(frontFile, backFile?)` |

---

## Styling

- **CSS Modules** — every component has a corresponding `.module.css`. Class names are scoped automatically.
- **CSS variables** — colors, spacing, fonts defined in `index.css` / `:root`. Dark theme by default.
- **Compact mode** — `body.compact` class reduces padding/font-size across all table rows.
- **No CSS framework** — all styles hand-written.

Key CSS variable names: `--bg-primary`, `--bg-card`, `--bg-secondary`, `--border`, `--text-primary`, `--text-secondary`, `--text-muted`, `--accent`, `--accent-muted`, `--accent-border`, `--success`, `--danger`.
