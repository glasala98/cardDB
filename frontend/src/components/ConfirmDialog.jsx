import styles from './ConfirmDialog.module.css'

export default function ConfirmDialog({ message, onConfirm, onCancel, confirmLabel = 'Confirm', danger = false }) {
  return (
    <div className={styles.overlay} onClick={onCancel}>
      <div className={styles.dialog} onClick={e => e.stopPropagation()}>
        <p className={styles.message}>{message}</p>
        <div className={styles.actions}>
          <button className={styles.cancel} onClick={onCancel}>Cancel</button>
          <button className={`${styles.confirm} ${danger ? styles.danger : ''}`} onClick={onConfirm}>
            {confirmLabel}
          </button>
        </div>
      </div>
    </div>
  )
}
