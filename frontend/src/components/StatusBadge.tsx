import type { WorkItemState } from '../api/types'
import { isRunning, STATE_LABEL } from '../lib/workitem'
import styles from './StatusBadge.module.css'

type Tone = 'running' | 'done' | 'error' | 'muted'

function toneFor(state: WorkItemState): Tone {
  if (state === 'DONE') return 'done'
  if (state === 'FAILED') return 'error'
  if (state === 'WAIT_HUMAN') return 'running'
  if (isRunning(state)) return 'running'
  return 'muted'
}

export function StatusBadge({ state }: { state: WorkItemState }) {
  const tone = toneFor(state)
  return (
    <span className={styles.badge}>
      <span className={styles.dot} data-tone={tone} aria-hidden="true" />
      {STATE_LABEL[state]}
    </span>
  )
}
