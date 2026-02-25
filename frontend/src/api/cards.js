import client from './client'

export const getCards            = ()           => client.get('/cards')
export const getCardDetail       = (name)       => client.get(`/cards/${encodeURIComponent(name)}`)
export const getPortfolioHistory = ()           => client.get('/cards/portfolio-history')
export const getArchive          = ()           => client.get('/cards/archive')

export const addCard     = (data)       => client.post('/cards', data)
export const updateCard  = (name, data) => client.patch(`/cards/${encodeURIComponent(name)}`, data)
export const archiveCard = (name)       => client.delete(`/cards/${encodeURIComponent(name)}`)
export const restoreCard = (name)       => client.post(`/cards/restore/${encodeURIComponent(name)}`)
export const scrapeCard  = (name)       => client.post(`/cards/${encodeURIComponent(name)}/scrape`)
