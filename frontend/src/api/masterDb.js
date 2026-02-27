import client from './client'

/** Get all Young Guns cards from master DB. */
export const getYoungGuns = (params = {}) =>
  client.get('/master-db', { params })

/** Get price history for a specific card in master DB. */
export const getYGPriceHistory = (cardName) =>
  client.get(`/master-db/price-history/${encodeURIComponent(cardName)}`)

/** Get NHL player stats. */
export const getNHLStats = () => client.get('/master-db/nhl-stats')

/** Get portfolio history for master DB. */
export const getYGPortfolioHistory = () =>
  client.get('/master-db/portfolio-history')

/** Get top market movers (gainers + losers) from YG price history. */
export const getMarketMovers = () => client.get('/master-db/market-movers')

/** Get seasonal price trends from YG price history. */
export const getSeasonalTrends = () => client.get('/master-db/seasonal-trends')

/** Get PSA/BGS graded prices for a player (for ROI calculator). */
export const getGradingLookup = (player) => client.get(`/master-db/grading-lookup/${encodeURIComponent(player)}`)

/** Get YG price history for a specific card (query-param, safe for special chars). */
export const getYGPriceHistoryByName = (name) =>
  client.get('/master-db/yg-price-history', { params: { name } })

/** Update owned / cost_basis / purchase_date for a YG card. */
export const updateYGOwnership = (player, season, data) =>
  client.patch('/master-db/ownership', data, { params: { player, season } })

/** Trigger a background eBay re-scrape for a single YG card. */
export const scrapeYGCard = (player, season) =>
  client.post('/master-db/scrape', null, { params: { player, season } })
