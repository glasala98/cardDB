import client from './client'

export const getUsers        = ()                    => client.get('/admin/users')
export const createUser      = (data)                => client.post('/admin/users', data)
export const deleteUser      = (username)            => client.delete(`/admin/users/${encodeURIComponent(username)}`)
export const changePassword  = (username, password)  => client.patch(`/admin/users/${encodeURIComponent(username)}/password`, { password })
export const changeRole      = (username, role)      => client.patch(`/admin/users/${encodeURIComponent(username)}/role`, { role })

export const toggleIgnore    = (priceId)             => client.patch(`/admin/market-prices/${priceId}/ignore`)
export const getOutliers     = (limit = 50)          => client.get('/admin/outliers', { params: { limit } })
export const getPipelineHealth = ()                  => client.get('/admin/pipeline-health')
export const getWorkflowStatus = ()                  => client.get('/stats/workflow-status')
export const getScrapeRuns        = (limit = 50, workflow = null) => client.get('/admin/scrape-runs', { params: { limit, ...(workflow && { workflow }) } })
export const getScrapeRunsSummary = ()                            => client.get('/admin/scrape-runs/summary')
export const getDataQuality       = ()                            => client.get('/admin/data-quality')
export const getSnapshotAudit     = (tier = 'staple', sport = null, limit = 25) =>
  client.get('/admin/snapshot-audit', { params: { tier, ...(sport && { sport }), limit } })

export const getScrapeRunErrors     = (runId, limit = 100) => client.get(`/admin/scrape-runs/${runId}/errors`, { params: { limit } })

export const getSealedProductsAdmin  = (params = {}) => client.get('/admin/sealed-products', { params })
export const updateSealedProduct     = (id, data)    => client.patch(`/admin/sealed-products/${id}`, data)
export const getSealedQuality        = ()             => client.get('/admin/sealed-products/quality')
export const deleteSealedMismatches  = ()             => client.delete('/admin/sealed-products/mismatches')

export const triggerWorkflow    = (workflowFile, inputs = {}) => client.post('/admin/trigger-workflow', { workflow_file: workflowFile, inputs })
export const bulkIgnoreOutliers = (ids)                       => client.post('/admin/outliers/bulk-ignore', { ids })
