import client from './client'

export const triggerScrape  = () => client.post('/stats/trigger-scrape')
export const getScrapeStatus = () => client.get('/stats/scrape-status')
