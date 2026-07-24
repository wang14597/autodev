import type { Project } from '../api/types'
import { EmptyStage } from './EmptyStage'
import { ProjectCard } from './ProjectCard'
import styles from './ProjectList.module.css'

export function ProjectList({ items }: { items: Project[] }) {
  if (items.length === 0) {
    return <EmptyStage message="还没有项目。创建第一个项目开始。" />
  }

  return (
    <ul className={styles.list}>
      {items.map((project) => (
        <li key={project.id}>
          <ProjectCard project={project} />
        </li>
      ))}
    </ul>
  )
}
