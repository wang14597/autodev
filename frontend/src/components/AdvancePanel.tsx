import type { NextAction } from '../api/types'
import styles from './AdvancePanel.module.css'

interface AdvancePanelProps {
  nextAction: NextAction
  nextStage: string | null
  onAdvance: () => void
  isPending: boolean
}

export function AdvancePanel({ nextAction, nextStage, onAdvance, isPending }: AdvancePanelProps) {
  // decide 交人审面板处理；none 是终态，无操作可做。
  if (nextAction === 'decide' || nextAction === 'none') {
    return null
  }

  const blocked = nextAction === 'blocked'
  const stage = nextStage ?? '下一阶段'

  return (
    <section className={styles.panel} data-testid="advance-panel">
      <p className={styles.title}>推进</p>
      <p className={styles.hint}>
        {blocked ? `「${stage}」阶段尚未建设，暂时无法继续。` : `下一步将执行「${stage}」阶段。`}
      </p>
      <button
        type="button"
        className={styles.button}
        data-testid="advance-button"
        disabled={blocked || isPending}
        onClick={onAdvance}
      >
        {isPending ? '推进中…' : '推进下一步 →'}
      </button>
    </section>
  )
}
