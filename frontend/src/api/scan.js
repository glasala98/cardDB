import client from './client'

/**
 * Send front (and optional back) card images to Claude Vision for analysis.
 * @param {File} frontFile
 * @param {File|null} backFile
 */
export const analyzeCard = (frontFile, backFile = null) => {
  const form = new FormData()
  form.append('front', frontFile)
  if (backFile) form.append('back', backFile)
  return client.post('/scan/analyze', form, {
    headers: { 'Content-Type': 'multipart/form-data' },
  })
}
