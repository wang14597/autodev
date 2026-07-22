import { useParams } from 'react-router-dom'
import { ApiError } from '../api/client'
import { BriefDocument } from '../components/BriefDocument'
import { EmptyStage } from '../components/EmptyStage'
import { FailurePanel } from '../components/FailurePanel'
import { LifelinePipeline } from '../components/LifelinePipeline'
import { Notice } from '../components/Notice'
import { StatusBadge } from '../components/StatusBadge'
import { useWorkItem } from '../hooks/useWorkItem'
import styles from './WorkItemDetailPage.module.css'

export function WorkItemDetailPage() {
  const { id } = useParams<{ id: string }>()
  const { data: detail, isError, error, isLoading } = useWorkItem(id)

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

      <section className={styles.section}>
        <p className={styles.sectionTitle}>生命周期</p>
        <LifelinePipeline stages={detail.stages} state={detail.state} />
      </section>

      {detail.context && (
        <BriefDocument
          markdown={detail.context.markdown}
          contextFile={detail.context.context_file}
        />
      )}

      {detail.failure && <FailurePanel reason={detail.failure.reason} />}
    </div>
  )
}
