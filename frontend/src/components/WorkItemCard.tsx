import { NavLink } from 'react-router-dom'
import type { WorkItemSummary } from '../api/types'
import { formatShortTime } from '../lib/workitem'
import { StatusBadge } from './StatusBadge'
import styles from './WorkItemCard.module.css'

export function WorkItemCard({ item }: { item: WorkItemSummary }) {
  return (
    <NavLink
      to={`/workitems/${item.id}`}
      className={({ isActive }) => `${styles.card} ${isActive ? styles.active : ''}`.trim()}
    >
      <p className={styles.goal}>{item.goal}</p>
      <div className={styles.meta}>
        <span className={styles.repo}>{item.repo}</span>
        <StatusBadge state={item.state} />
        <time className={styles.time} dateTime={item.updated_at ?? undefined}>
          {formatShortTime(item.updated_at ?? item.created_at)}
        </time>
      </div>
    </NavLink>
  )
}
