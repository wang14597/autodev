import { Outlet } from 'react-router-dom'
import { AppHeader } from '../components/AppHeader'
import { NewWorkItemForm } from '../components/NewWorkItemForm'
import { Notice } from '../components/Notice'
import { WorkItemList } from '../components/WorkItemList'
import { useWorkItems } from '../hooks/useWorkItems'
import styles from './DashboardPage.module.css'

export function DashboardPage() {
  const { data: items, isError } = useWorkItems()

  return (
    <>
      <AppHeader />
      <div className={styles.layout}>
        <aside className={styles.rail}>
          <div className={styles.railHeader}>
            <span className={styles.railTitle}>新建工作项</span>
            <NewWorkItemForm />
          </div>
          <div className={styles.railHeader}>
            <span className={styles.railTitle}>工作项</span>
            {isError && <Notice message="工作项列表加载失败，请稍后重试。" />}
            <WorkItemList items={items ?? []} />
          </div>
        </aside>
        <main className={styles.main}>
          <Outlet />
        </main>
      </div>
    </>
  )
}
