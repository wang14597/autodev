import { ApiError } from '../api/client'
import type { Project } from '../api/types'
import { useDeleteProject } from '../hooks/useDeleteProject'
import { useRefreshProject } from '../hooks/useRefreshProject'
import styles from './ProjectHeader.module.css'

export function ProjectHeader({ project }: { project: Project }) {
  const refresh = useRefreshProject(project.id)
  const del = useDeleteProject()

  function handleDelete() {
    const confirmed = window.confirm(
      `确定要删除项目「${project.name}」吗？其下所有工作项也会被一并删除，且不可恢复。`,
    )
    if (confirmed) {
      del.mutate(project.id)
    }
  }

  const refreshError =
    refresh.error instanceof ApiError ? refresh.error.detail : refresh.error?.message
  const deleteError = del.error instanceof ApiError ? del.error.detail : del.error?.message

  return (
    <header className={styles.header}>
      <div className={styles.row}>
        <div className={styles.identity}>
          <p className={styles.name}>{project.name}</p>
          <p className={styles.meta}>
            <span className={styles.repo}>{project.repo_source}</span>
            <span className={styles.branch}>默认分支 {project.default_branch ?? '未探测'}</span>
          </p>
        </div>
        <div className={styles.actions}>
          <button
            type="button"
            className={styles.refreshButton}
            onClick={() => refresh.mutate()}
            disabled={refresh.isPending}
          >
            {refresh.isPending ? '刷新中…' : '刷新'}
          </button>
          <button
            type="button"
            className={styles.deleteButton}
            onClick={handleDelete}
            disabled={del.isPending}
          >
            {del.isPending ? '删除中…' : '删除项目'}
          </button>
        </div>
      </div>
      {refreshError && <p className={styles.error}>刷新失败：{refreshError}</p>}
      {deleteError && <p className={styles.error}>删除失败：{deleteError}</p>}
    </header>
  )
}
