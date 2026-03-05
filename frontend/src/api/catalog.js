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
