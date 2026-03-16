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

/** Get individual eBay sold listings from market_raw_sales for a catalog card. */
export const getCatalogRawSales = (catalogId, offset = 0, limit = 50) =>
  client.get(`/catalog/${catalogId}/raw-sales`, { params: { offset, limit } })

/** Natural-language AI card search — Claude parses the query into filters. */
export const aiSearchCatalog = (q) =>
  client.get('/catalog/ai-search', { params: { q } })
