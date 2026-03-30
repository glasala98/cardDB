import client from './client'

export const getEbayStatus   = ()          => client.get('/ebay/status')
export const getEbayPrefill  = (cardName)  => client.get('/ebay/prefill', { params: { card_name: cardName } })
export const createEbayDraft = (data)      => client.post('/ebay/create-draft', data)
export const getEbayDrafts   = ()          => client.get('/ebay/drafts')
export const disconnectEbay  = ()          => client.post('/ebay/disconnect')
