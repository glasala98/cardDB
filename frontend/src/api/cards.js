import client from './client'

/** Get all cards for the current user (summary table). */
export const getCards = () => client.get('/cards')

/** Get full detail for a single card (price history, raw sales, confidence). */
export const getCardDetail = (cardName) =>
  client.get(`/cards/${encodeURIComponent(cardName)}`)

/** Trigger a re-scrape for a single card. */
export const scrapeCard = (cardName) =>
  client.post(`/cards/${encodeURIComponent(cardName)}/scrape`)

/** Get portfolio history snapshots. */
export const getPortfolioHistory = () => client.get('/cards/portfolio-history')
