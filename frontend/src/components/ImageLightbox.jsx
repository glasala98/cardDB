import { useEffect } from 'react'
import styles from './ImageLightbox.module.css'

export default function ImageLightbox({ src, alt, onClose }) {
  useEffect(() => {
    const handler = e => { if (e.key === 'Escape') onClose() }
    window.addEventListener('keydown', handler)
    document.body.style.overflow = 'hidden'
    return () => {
      window.removeEventListener('keydown', handler)
      document.body.style.overflow = ''
    }
  }, [onClose])

  return (
    <div className={styles.overlay} onClick={onClose}>
      <button className={styles.closeBtn} onClick={onClose}>✕</button>
      <img
        className={styles.img}
        src={src}
        alt={alt}
        onClick={e => e.stopPropagation()}
      />
    </div>
  )
}
