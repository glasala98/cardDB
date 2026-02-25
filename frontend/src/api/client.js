import axios from 'axios'

const client = axios.create({
  baseURL: '/api',
  timeout: 30000,
  headers: { 'Content-Type': 'application/json' },
})

client.interceptors.response.use(
  res => res.data,
  err => {
    const msg = err.response?.data?.detail || err.message || 'Unknown error'
    return Promise.reject(new Error(msg))
  }
)

export default client
