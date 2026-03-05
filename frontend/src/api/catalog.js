import client from './client'

/** Browse the card catalog with filters and pagination. */
export const getCatalog = (params = {}) =>
  client.get('/catalog', { params })

/** Get filter dropdown options (sports, years, sets). */
export const getCatalogFilters = (sport = null) =>
  client.get('/catalog/filters', { params: sport ? { sport } : {} })
