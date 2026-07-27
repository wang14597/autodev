import type { RiskLevel, TriageView } from '../api/types'
import styles from './TriageBadge.module.css'

const RISK_LABEL: Record<RiskLevel, string> = {
  LOW: '低',
  MEDIUM: '中',
  HIGH: '高',
}

export function TriageBadge({ triage }: { triage: TriageView }) {
  return (
    <div className={styles.wrap}>
      <span className={styles.risk} data-risk={triage.risk} data-testid="triage-risk">
        风险 {triage.risk}
        <span className={styles.riskCn}>（{RISK_LABEL[triage.risk]}）</span>
      </span>
      <span className={styles.confidence}>置信 {Math.round(triage.confidence * 100)}%</span>
      {triage.signals.length > 0 && (
        <ul className={styles.signals}>
          {triage.signals.map((s) => (
            <li key={s} className={styles.signal}>
              {s}
            </li>
          ))}
        </ul>
      )}
    </div>
  )
}
