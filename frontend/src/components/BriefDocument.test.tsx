import { render, screen } from '@testing-library/react'
import { describe, expect, it } from 'vitest'
import { BriefDocument } from './BriefDocument'

describe('BriefDocument', () => {
  it('renders sanitized markdown as HTML', () => {
    const { container } = render(
      <BriefDocument markdown={'# 标题\n\n正文段落。'} path="/tmp/ctx.md" />,
    )
    expect(container.querySelector('h1')?.textContent).toBe('标题')
    expect(container.textContent).toContain('正文段落。')
    expect(container.textContent).toContain('/tmp/ctx.md')
  })

  it('is collapsible: renders a <details>/<summary>, open by default', () => {
    const { container } = render(<BriefDocument markdown={'# 标题'} path="/tmp/ctx.md" />)
    const details = container.querySelector('details')
    expect(details).not.toBeNull()
    expect(details?.open).toBe(true) // 默认展开
    const summary = container.querySelector('summary')
    expect(summary?.textContent).toContain('上下文简报')
  })

  it('strips <script> tags injected via markdown/HTML', () => {
    const { container } = render(
      <BriefDocument
        markdown={'safe text\n\n<script>window.__pwned = true</script>'}
        path="ctx.md"
      />,
    )
    expect(container.querySelector('script')).not.toBeInTheDocument()
    expect(container.innerHTML).not.toContain('<script>')
  })

  it('strips onerror/onclick event handler attributes', () => {
    const { container } = render(
      <BriefDocument markdown={'<img src="x" onerror="window.__pwned=true">'} path="ctx.md" />,
    )
    const img = container.querySelector('img')
    expect(img).not.toBeNull()
    expect(img?.getAttribute('onerror')).toBeNull()
  })

  it('renders a custom title (方案)', () => {
    render(<BriefDocument title="方案" markdown={'## 方案概述\n改 app.py'} path="/x/design.md" />)
    expect(screen.getByText('方案')).toBeInTheDocument()
    expect(screen.getByText('/x/design.md')).toBeInTheDocument()
  })
})
