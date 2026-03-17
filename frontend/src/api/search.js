import client from './client'

/** Full-text search across all scraped sales. */
export const searchSales = (params = {}) =>
  client.get('/search', { params })

/** Autocomplete suggestions from card_catalog. */
export const getSearchSuggestions = (q) =>
  client.get('/search/suggest', { params: { q } })

/** Active data sources with sale counts. */
export const getSearchSources = () =>
  client.get('/search/sources')
