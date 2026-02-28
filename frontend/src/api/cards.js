import client from './client'

export const getCards            = ()           => client.get('/cards')
export const getCardDetail       = (name)       => client.get('/cards/detail', { params: { name } })
export const getPortfolioHistory = ()           => client.get('/cards/portfolio-history')
export const getArchive          = ()           => client.get('/cards/archive')

export const addCard        = (data)       => client.post('/cards', data)
export const updateCard     = (name, data) => client.patch('/cards/update', data, { params: { name } })
export const archiveCard    = (name)       => client.delete('/cards/archive', { params: { name } })
export const restoreCard    = (name)       => client.post('/cards/restore', null, { params: { name } })
export const scrapeCard     = (name)       => client.post('/cards/scrape', null, { params: { name } })
export const fetchImage     = (name)       => client.post('/cards/fetch-image', null, { params: { name } })
export const getCardOfTheDay = ()          => client.get('/cards/card-of-the-day')
export const bulkImport     = (file)       => {
  const form = new FormData()
  form.append('file', file)
  return client.post('/cards/bulk-import', form, { headers: { 'Content-Type': 'multipart/form-data' } })
}
