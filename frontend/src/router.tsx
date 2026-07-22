import { createBrowserRouter } from 'react-router-dom'

// Placeholder scaffold router — replaced with the full WorkItem console router in Part B.
function Placeholder() {
  return <p>AutoDev 控制台</p>
}

export const router = createBrowserRouter([
  {
    path: '/',
    element: <Placeholder />,
  },
])
