import { useEffect } from 'react'

export default function EbayConnected() {
  useEffect(() => {
    window.close()
  }, [])
  return (
    <div style={{ padding: 40, textAlign: 'center', color: '#aaa', fontFamily: 'sans-serif' }}>
      <p>eBay connected. You may close this window.</p>
    </div>
  )
}
