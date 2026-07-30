import { Link, useParams } from 'react-router-dom'
import { ApiError } from '../api/client'
import { BriefDocument } from '../components/BriefDocument'
import { EmptyStage } from '../components/EmptyStage'
import { FailurePanel } from '../components/FailurePanel'
import { LifelinePipeline } from '../components/LifelinePipeline'
import { Notice } from '../components/Notice'
import { StatusBadge } from '../components/StatusBadge'
import { TriageBadge } from '../components/TriageBadge'
import { useDecideWorkItem } from '../hooks/useDecideWorkItem'
import { useWorkItem } from '../hooks/useWorkItem'
import styles from './WorkItemDetailPage.module.css'

export function WorkItemDetailPage() {
  const { pid, id } = useParams<{ pid: string; id: string }>()
  const { data: detail, isError, error, isLoading } = useWorkItem(id)
  const decide = useDecideWorkItem(id)

  if (isError) {
    if (error instanceof ApiError && error.status === 404) {
      return <EmptyStage message="未找到该工作项，它可能已被删除。" />
    }
    return <Notice message="工作项详情加载失败，请稍后重试。" />
  }

  if (isLoading || !detail) {
    return <EmptyStage message="加载中…" />
  }

  return (
    <div className={styles.page}>
      {pid && (
        <Link to={`/projects/${pid}`} className={styles.back}>
          ← 返回项目
        </Link>
      )}

      <section className={styles.overview}>
        <p className={styles.goal}>{detail.goal}</p>
        <div className={styles.metaRow}>
          <span className={styles.metaItem}>
            项目 <span className={styles.metaValue}>{detail.repo}</span>
          </span>
          <span className={styles.metaItem}>
            类型 <span className={styles.metaValue}>{detail.type ?? '—'}</span>
          </span>
          <StatusBadge state={detail.state} />
        </div>
      </section>

      {detail.triage && (
        <section className={styles.section}>
          <p className={styles.sectionTitle}>分诊</p>
          <TriageBadge triage={detail.triage} />
        </section>
      )}

      {detail.state === 'WAIT_HUMAN' && (
        <section className={styles.section} data-testid="approval-panel">
          <p className={styles.sectionTitle}>人审门禁</p>
          {detail.pending_gate === 'CONTEXT_GATE' ? (
            <>
              <p className={styles.gateHint}>
                上下文已收集完成。是否继续走后续开发流程，还是就此完成（仅收集需求）？
              </p>
              <div className={styles.gateActions}>
                <button
                  type="button"
                  className={styles.approveBtn}
                  data-testid="approve-button"
                  disabled={decide.isPending}
                  onClick={() => decide.mutate('proceed')}
                >
                  继续后续流程
                </button>
                <button
                  type="button"
                  className={styles.denyBtn}
                  data-testid="close-button"
                  disabled={decide.isPending}
                  onClick={() => decide.mutate('close')}
                >
                  完成（仅收集）
                </button>
                <button
                  type="button"
                  className={styles.denyBtn}
                  disabled={decide.isPending}
                  onClick={() => decide.mutate('reject')}
                >
                  拒绝
                </button>
              </div>
            </>
          ) : (
            <>
              <p className={styles.gateHint}>该工作项风险偏高或置信不足，已挂起等待人工确认。</p>
              <div className={styles.gateActions}>
                <button
                  type="button"
                  className={styles.approveBtn}
                  data-testid="approve-button"
                  disabled={decide.isPending}
                  onClick={() => decide.mutate('proceed')}
                >
                  批准继续
                </button>
                <button
                  type="button"
                  className={styles.denyBtn}
                  disabled={decide.isPending}
                  onClick={() => decide.mutate('reject')}
                >
                  拒绝
                </button>
              </div>
            </>
          )}
        </section>
      )}

      <section className={styles.section}>
        <p className={styles.sectionTitle}>生命周期</p>
        <LifelinePipeline stages={detail.stages} state={detail.state} />
      </section>

      {detail.context && (
        <BriefDocument
          title="上下文简报"
          markdown={detail.context.markdown}
          path={detail.context.context_file}
        />
      )}

      {detail.design && (
        <BriefDocument
          title="方案"
          markdown={detail.design.markdown}
          path={detail.design.design_file}
        />
      )}

      {detail.failure && <FailurePanel reason={detail.failure.reason} />}
    </div>
  )
}
