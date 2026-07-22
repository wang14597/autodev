import type { WorkItemSummary } from '../api/types'
import { EmptyStage } from './EmptyStage'
import { WorkItemCard } from './WorkItemCard'
import styles from './WorkItemList.module.css'

export function WorkItemList({ items }: { items: WorkItemSummary[] }) {
  if (items.length === 0) {
    return <EmptyStage message="还没有工作项。在上面创建第一个。" />
  }

  return (
    <ul className={styles.list}>
      {items.map((item) => (
        <li key={item.id}>
          <WorkItemCard item={item} />
        </li>
      ))}
    </ul>
  )
}
