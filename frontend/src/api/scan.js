/**
 * Send front (and optional back) card images to Claude Vision for analysis.
 * Uses fetch instead of the axios client to avoid Content-Type/boundary issues:
 * axios v1+ AxiosHeaders makes it impossible to reliably clear the default
 * 'application/json' Content-Type, which breaks multipart form parsing.
 * fetch + FormData always auto-sets the correct multipart boundary.
 *
 * @param {File} frontFile
 * @param {File|null} backFile
 */
export const analyzeCard = async (frontFile, backFile = null) => {
  const form = new FormData()
  form.append('front', frontFile)
  if (backFile) form.append('back', backFile)

  // Include auth token if present (scan endpoint is unprotected, but good practice)
  const token = localStorage.getItem('auth_token')
  const headers = token ? { Authorization: `Bearer ${token}` } : {}

  const res = await fetch('/api/scan/analyze', {
    method: 'POST',
    body: form,   // No Content-Type — browser auto-sets multipart/form-data + boundary
    headers,
    signal: AbortSignal.timeout(60000),
  })

  if (!res.ok) {
    const data = await res.json().catch(() => ({}))
    const detail = data.detail
    const msg = typeof detail === 'string'
      ? detail
      : Array.isArray(detail)
        ? detail.map(d => d.msg ?? JSON.stringify(d)).join(', ')
        : `HTTP ${res.status}`
    throw new Error(msg)
  }

  return res.json()
}
