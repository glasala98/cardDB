import client from './client'

export const login   = (username, password) => client.post('/auth/login', { username, password })
export const getMe   = ()                   => client.get('/auth/me')
export const logout  = ()                   => client.post('/auth/logout')
