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
