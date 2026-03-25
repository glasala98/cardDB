/**
 * Wraps an eBay URL with the EPN affiliate tracking parameters.
 * Returns the original URL unchanged if it's not an eBay URL or is empty.
 */
const CAMPAIGN_ID = import.meta.env.VITE_EBAY_CAMPAIGN_ID || '5339146476'
const TOOL_ID     = '10001'
const MKRID       = '711-53200-19255-0'  // eBay US

export function ebayAffiliateUrl(url) {
  if (!url || !url.includes('ebay.com')) return url
  try {
    const rover = new URL('https://rover.ebay.com/rover/1/' + MKRID + '/1')
    rover.searchParams.set('mpre',    url)
    rover.searchParams.set('campid',  CAMPAIGN_ID)
    rover.searchParams.set('toolid',  TOOL_ID)
    rover.searchParams.set('mkevt',   '1')
    return rover.toString()
  } catch {
    return url
  }
}
