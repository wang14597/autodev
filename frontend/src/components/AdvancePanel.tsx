import type { NextAction } from '../api/types'
import styles from './AdvancePanel.module.css'

interface AdvancePanelProps {
  nextAction: NextAction
  nextStage: string | null
  onAdvance: () => void
  isPending: boolean
}

export function AdvancePanel({ nextAction, nextStage, onAdvance, isPending }: AdvancePanelProps) {
  // 白名单而非排除法，且失败时闭合。只有明确知道"下一步是哪个阶段"才渲染控件：
  //   - decide 交人审三键面板；none 是终态，都无操作可做
  //   - 取值不认识（后端版本不一致、字段缺失 → 运行时为 undefined，`request` 的
  //     `as T` 不做校验拦不住），或 advance/blocked 却拿不到阶段名 —— 一律什么都不渲染
  // 宁可不给按钮，也不能在不知道下一步是什么的时候摆一个可点的按钮 + 占位文案出来：
  // 那正是本功能要消灭的"呈现一个错误的可操作提示"。
  const actionable = nextAction === 'advance' || nextAction === 'blocked'
  if (!actionable || !nextStage) {
    return null
  }

  const blocked = nextAction === 'blocked'

  return (
    <section className={styles.panel} data-testid="advance-panel">
      <p className={styles.title}>推进</p>
      <p className={styles.hint}>
        {blocked
          ? `「${nextStage}」阶段尚未建设，暂时无法继续。`
          : `下一步将执行「${nextStage}」阶段。`}
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
