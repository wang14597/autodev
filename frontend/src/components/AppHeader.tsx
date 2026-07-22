import styles from './AppHeader.module.css'

/**
 * Faint contour texture behind the header copy — purely decorative, hidden
 * from assistive tech. Evokes a survey-instrument dial without adding noise.
 */
function ContourTexture() {
  return (
    <svg
      className={styles.texture}
      aria-hidden="true"
      focusable="false"
      viewBox="0 0 600 200"
      preserveAspectRatio="none"
    >
      <circle cx="520" cy="40" r="20" fill="none" stroke="currentColor" strokeWidth="1" />
      <circle cx="520" cy="40" r="48" fill="none" stroke="currentColor" strokeWidth="1" />
      <circle cx="520" cy="40" r="76" fill="none" stroke="currentColor" strokeWidth="1" />
      <circle cx="520" cy="40" r="104" fill="none" stroke="currentColor" strokeWidth="1" />
      <path
        d="M0 150 Q150 110 300 150 T600 150"
        fill="none"
        stroke="currentColor"
        strokeWidth="1"
      />
      <path
        d="M0 175 Q150 135 300 175 T600 175"
        fill="none"
        stroke="currentColor"
        strokeWidth="1"
      />
    </svg>
  )
}

export function AppHeader() {
  return (
    <header className={styles.header}>
      <ContourTexture />
      <div className={styles.content}>
        <span className={styles.wordmark}>AutoDev</span>
        <p className={styles.eyebrow}>AI 研发工作流 · 工作台</p>
        <h1 className={styles.title}>创建工作项，让 Claude 读懂代码再动手</h1>
      </div>
    </header>
  )
}
