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
