import client from './client'

export function getGradingAdvice(payload) {
  return client.post('/ai/grading-advice', payload)
}
