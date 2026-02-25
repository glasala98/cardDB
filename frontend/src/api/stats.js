import client from './client'

export const triggerScrape = () => client.post('/stats/trigger-scrape')
