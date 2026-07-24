import { AppHeader } from '../components/AppHeader'
import { NewProjectForm } from '../components/NewProjectForm'
import { Notice } from '../components/Notice'
import { ProjectList } from '../components/ProjectList'
import { useProjects } from '../hooks/useProjects'
import styles from './ProjectsPage.module.css'

export function ProjectsPage() {
  const { data: projects, isError } = useProjects()

  return (
    <>
      <AppHeader />
      <div className={styles.layout}>
        <aside className={styles.rail}>
          <span className={styles.railTitle}>新建项目</span>
          <NewProjectForm />
        </aside>
        <main className={styles.main}>
          <span className={styles.railTitle}>项目</span>
          {isError && <Notice message="项目列表加载失败，请稍后重试。" />}
          <ProjectList items={projects ?? []} />
        </main>
      </div>
    </>
  )
}
