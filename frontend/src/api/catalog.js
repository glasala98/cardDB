import client from './client'

/** Browse the card catalog with filters and pagination. */
export const getCatalog = (params = {}) =>
  client.get('/catalog', { params })

/** Get filter dropdown options (sports, years, sets). */
export const getCatalogFilters = (sport = null, year = null) => {
  const params = {}
  if (sport) params.sport = sport
  if (year)  params.year  = year
  return client.get('/catalog/filters', { params })
}

/** Get price history for a single catalog card. */
export const getCatalogCardHistory = (catalogId) =>
  client.get(`/catalog/${catalogId}/history`)

/** Get recently indexed sets for the Releases page. */
export const getNewReleases = (params = {}) =>
  client.get('/catalog/releases', { params })

/** Get sealed product info (MSRP, pack config, odds) for matching sets. */
export const getSealedProducts = (params = {}) =>
  client.get('/catalog/sealed-products', { params })

/** Get a single catalog card's info and current market price. */
export const getCatalogCard = (catalogId) =>
  client.get(`/catalog/${catalogId}`)

/** Get individual sold listings from market_raw_sales for a catalog card, with filters. */
export const getCatalogRawSales = (catalogId, params = {}) =>
  client.get(`/catalog/${catalogId}/raw-sales`, { params })

/** Natural-language AI card search — Claude parses the query into filters. */
export const aiSearchCatalog = (q) =>
  client.get('/catalog/ai-search', { params: { q } })

/** Parse a natural-language query into structured fields (player, year, set, variant). */
export const parseCardQuery = (q) =>
  client.get('/catalog/parse', { params: { q } })
