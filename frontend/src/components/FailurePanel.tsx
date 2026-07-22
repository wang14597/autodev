import styles from './FailurePanel.module.css'

export function FailurePanel({ reason }: { reason: string }) {
  return (
    <section className={styles.panel} role="alert">
      <p className={styles.title}>工作项失败</p>
      <p className={styles.reason}>{reason}</p>
      <p className={styles.hint}>检查项目是否已登记、网络/网关是否可达。</p>
    </section>
  )
}
