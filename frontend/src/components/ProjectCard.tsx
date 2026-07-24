import { NavLink } from 'react-router-dom'
import type { Project } from '../api/types'
import { formatShortTime } from '../lib/workitem'
import styles from './ProjectCard.module.css'

export function ProjectCard({ project }: { project: Project }) {
  return (
    <NavLink
      to={`/projects/${project.id}`}
      className={({ isActive }) => `${styles.card} ${isActive ? styles.active : ''}`.trim()}
    >
      <p className={styles.name}>{project.name}</p>
      <p className={styles.repo}>{project.repo_source}</p>
      <div className={styles.meta}>
        <span className={styles.branch}>{project.default_branch ?? '未探测分支'}</span>
        <span className={styles.count}>{project.workitem_count} 个工作项</span>
        <time className={styles.time} dateTime={project.created_at ?? undefined}>
          {formatShortTime(project.created_at)}
        </time>
      </div>
    </NavLink>
  )
}
