import client from './client'

export const getUsers        = ()                    => client.get('/admin/users')
export const createUser      = (data)                => client.post('/admin/users', data)
export const deleteUser      = (username)            => client.delete(`/admin/users/${encodeURIComponent(username)}`)
export const changePassword  = (username, password)  => client.patch(`/admin/users/${encodeURIComponent(username)}/password`, { password })
