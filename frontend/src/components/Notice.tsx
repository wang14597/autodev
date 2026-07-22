import styles from './Notice.module.css'

/** Non-blocking banner for query errors — informs without taking over the page. */
export function Notice({ message }: { message: string }) {
  return (
    <div className={styles.notice} role="status">
      {message}
    </div>
  )
}
