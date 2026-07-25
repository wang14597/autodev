import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { RouterProvider } from 'react-router-dom'
import { ConfigProvider } from 'antd'

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

// antd v6 ships CSS-in-JS and natively supports React 19 — no `antd/dist/reset.css`
// import and no `@ant-design/v5-patch-for-react-19` shim needed here. Importing the
// reset stylesheet would also globally reset native elements (body margin, box-sizing,
// etc.), which would fight this app's own design tokens in styles/tokens.css and
// styles/global.css — so it is deliberately left out.
createRoot(document.getElementById('root')!).render(
  <StrictMode>
    <ConfigProvider
      theme={{
        token: {
          colorPrimary: '#d98a1f' /* --signal amber */,
          borderRadius: 6,
          colorText: '#17202e',
          fontFamily: 'inherit',
        },
      }}
    >
      <QueryClientProvider client={queryClient}>
        <RouterProvider router={router} />
      </QueryClientProvider>
    </ConfigProvider>
  </StrictMode>,
)
