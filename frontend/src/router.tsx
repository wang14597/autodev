import { createBrowserRouter } from 'react-router-dom'
import { ProjectDetailPage } from './pages/ProjectDetailPage'
import { ProjectsPage } from './pages/ProjectsPage'
import { WorkItemDetailPage } from './pages/WorkItemDetailPage'

export const router = createBrowserRouter([
  { path: '/', element: <ProjectsPage /> },
  { path: '/projects/:pid', element: <ProjectDetailPage /> },
  { path: '/projects/:pid/workitems/:id', element: <WorkItemDetailPage /> },
])
