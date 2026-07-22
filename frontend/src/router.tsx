import { createBrowserRouter } from 'react-router-dom'
import { DashboardPage } from './pages/DashboardPage'
import { StagePlaceholder } from './pages/StagePlaceholder'
import { WorkItemDetailPage } from './pages/WorkItemDetailPage'

export const router = createBrowserRouter([
  {
    path: '/',
    element: <DashboardPage />,
    children: [
      { index: true, element: <StagePlaceholder /> },
      { path: 'workitems/:id', element: <WorkItemDetailPage /> },
    ],
  },
])
