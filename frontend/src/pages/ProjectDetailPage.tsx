import { Link, useParams } from 'react-router-dom'
import { ApiError } from '../api/client'
import { EmptyStage } from '../components/EmptyStage'
import { NewWorkItemForm } from '../components/NewWorkItemForm'
import { Notice } from '../components/Notice'
import { ProjectHeader } from '../components/ProjectHeader'
import { WorkItemList } from '../components/WorkItemList'
import { useProject } from '../hooks/useProject'
import styles from './ProjectDetailPage.module.css'

export function ProjectDetailPage() {
  const { pid } = useParams<{ pid: string }>()
  const { data: detail, isError, error, isLoading } = useProject(pid)

  if (isError) {
    if (error instanceof ApiError && error.status === 404) {
      return <EmptyStage message="未找到该项目，它可能已被删除。" />
    }
    return <Notice message="项目详情加载失败，请稍后重试。" />
  }

  if (isLoading || !detail) {
    return <EmptyStage message="加载中…" />
  }

  return (
    <div className={styles.page}>
      <Link to="/" className={styles.back}>
        ← 所有项目
      </Link>

      <ProjectHeader project={detail} />

      <section className={styles.section}>
        <p className={styles.sectionTitle}>在此项目下新建工作项</p>
        <NewWorkItemForm projectId={detail.id} />
      </section>

      <section className={styles.section}>
        <p className={styles.sectionTitle}>工作项（{detail.workitem_count}）</p>
        <WorkItemList items={detail.workitems} projectId={detail.id} />
      </section>
    </div>
  )
}
