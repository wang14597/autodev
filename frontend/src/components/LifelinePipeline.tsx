import type { StageView, WorkItemState } from '../api/types'
import { isRunning } from '../lib/workitem'
import styles from './LifelinePipeline.module.css'

function DotGlyph({ status }: { status: StageView['status'] }) {
  if (status === 'done') return <span aria-hidden="true">✓</span>
  return null
}

/**
 * Vertical lifecycle steps for a WorkItem: done (green check), current
 * (amber, sonar ping only while the bounded driver is actively running),
 * pending (muted), blocked (greyed out, tagged 待建设 — not yet built).
 */
export function LifelinePipeline({ stages, state }: { stages: StageView[]; state: WorkItemState }) {
  const running = isRunning(state)

  return (
    <ol className={styles.pipeline}>
      {stages.map((stage) => (
        <li key={stage.key} className={styles.step}>
          <span className={styles.rail}>
            <span className={styles.dot} data-status={stage.status}>
              <DotGlyph status={stage.status} />
              {stage.status === 'current' && running && (
                <span className={styles.sonar} aria-hidden="true" />
              )}
            </span>
          </span>
          <span className={styles.body}>
            <span className={styles.label} data-status={stage.status}>
              {stage.label}
            </span>
            {stage.status === 'blocked' && <span className={styles.tag}>待建设</span>}
          </span>
        </li>
      ))}
    </ol>
  )
}
