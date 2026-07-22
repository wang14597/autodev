import styles from './EmptyStage.module.css'

export function EmptyStage({ message }: { message: string }) {
  return <p className={styles.empty}>{message}</p>
}
