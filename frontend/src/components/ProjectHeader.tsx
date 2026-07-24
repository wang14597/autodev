import type { ChangeEvent } from 'react'
import { ApiError } from '../api/client'
import type { Project } from '../api/types'
import { useDeleteProject } from '../hooks/useDeleteProject'
import { useProjectBranches } from '../hooks/useProjectBranches'
import { useRefreshProject } from '../hooks/useRefreshProject'
import { useSetProjectBranch } from '../hooks/useSetProjectBranch'
import styles from './ProjectHeader.module.css'

export function ProjectHeader({ project }: { project: Project }) {
  const refresh = useRefreshProject(project.id)
  const del = useDeleteProject()
  const branches = useProjectBranches(project.id)
  const setBranch = useSetProjectBranch(project.id)

  function handleDelete() {
    const confirmed = window.confirm(
      `确定要删除项目「${project.name}」吗？其下所有工作项也会被一并删除，且不可恢复。`,
    )
    if (confirmed) {
      del.mutate(project.id)
    }
  }

  function handleBranchChange(event: ChangeEvent<HTMLSelectElement>) {
    const next = event.target.value
    if (next && next !== project.branch) {
      setBranch.mutate(next)
    }
  }

  const refreshError =
    refresh.error instanceof ApiError ? refresh.error.detail : refresh.error?.message
  const deleteError = del.error instanceof ApiError ? del.error.detail : del.error?.message
  const branchError =
    setBranch.error instanceof ApiError ? setBranch.error.detail : setBranch.error?.message

  const fetchedBranches = branches.data ?? []
  const branchOptions = fetchedBranches.includes(project.branch)
    ? fetchedBranches
    : [project.branch, ...fetchedBranches]
  const canPickBranch = !branches.isLoading && branchOptions.length > 0

  return (
    <header className={styles.header}>
      <div className={styles.row}>
        <div className={styles.identity}>
          <p className={styles.name}>{project.name}</p>
          <p className={styles.meta}>
            <span className={styles.repo}>{project.repo_source}</span>
            <span className={styles.branchField}>
              <label htmlFor="project-branch-select" className={styles.branchLabel}>
                默认分支
              </label>
              {canPickBranch ? (
                <select
                  id="project-branch-select"
                  className={styles.branchSelect}
                  value={project.branch}
                  onChange={handleBranchChange}
                  disabled={setBranch.isPending}
                >
                  {branchOptions.map((name) => (
                    <option key={name} value={name}>
                      {name}
                    </option>
                  ))}
                </select>
              ) : (
                <span className={styles.branch}>{project.branch}</span>
              )}
              {setBranch.isPending && <span className={styles.hint}>切换中…</span>}
            </span>
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
      {branchError && <p className={styles.error}>切换分支失败：{branchError}</p>}
    </header>
  )
}
