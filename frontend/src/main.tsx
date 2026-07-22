import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { RouterProvider } from 'react-router-dom'

import '@fontsource-variable/space-grotesk'
import '@fontsource-variable/jetbrains-mono'
import '@fontsource/newsreader/400.css'
import '@fontsource/newsreader/500.css'
import '@fontsource/newsreader/600.css'

import './styles/tokens.css'
import './styles/global.css'

import { router } from './router'

const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      refetchOnWindowFocus: false,
      retry: 1,
    },
  },
})

createRoot(document.getElementById('root')!).render(
  <StrictMode>
    <QueryClientProvider client={queryClient}>
      <RouterProvider router={router} />
    </QueryClientProvider>
  </StrictMode>,
)
