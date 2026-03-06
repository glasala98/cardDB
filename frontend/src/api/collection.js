import client from './client'

export const getCollection     = ()           => client.get('/collection')
export const getOwnedIds       = ()           => client.get('/collection/owned-ids')
export const getGrades         = ()           => client.get('/collection/grades')
export const addToCollection   = (body)       => client.post('/collection', body)
export const updateCollectionItem = (id, body) => client.patch(`/collection/${id}`, body)
export const removeFromCollection = (id)      => client.delete(`/collection/${id}`)
