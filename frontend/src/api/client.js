import axios from 'axios'

const client = axios.create({
  baseURL: '/api',
  timeout: 30000,
  headers: { 'Content-Type': 'application/json' },
})

client.interceptors.response.use(
  res => res.data,
  err => {
    const detail = err.response?.data?.detail
    const msg = typeof detail === 'string'
      ? detail
      : Array.isArray(detail)
        ? detail.map(d => d.msg ?? JSON.stringify(d)).join(', ')
        : err.message || 'Unknown error'
    return Promise.reject(new Error(msg))
  }
)

export default client
