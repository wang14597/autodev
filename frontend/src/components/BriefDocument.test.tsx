import { render } from '@testing-library/react'
import { describe, expect, it } from 'vitest'
import { BriefDocument } from './BriefDocument'

describe('BriefDocument', () => {
  it('renders sanitized markdown as HTML', () => {
    const { container } = render(
      <BriefDocument markdown={'# 标题\n\n正文段落。'} contextFile="/tmp/ctx.md" />,
    )
    expect(container.querySelector('h1')?.textContent).toBe('标题')
    expect(container.textContent).toContain('正文段落。')
    expect(container.textContent).toContain('/tmp/ctx.md')
  })

  it('strips <script> tags injected via markdown/HTML', () => {
    const { container } = render(
      <BriefDocument
        markdown={'safe text\n\n<script>window.__pwned = true</script>'}
        contextFile="ctx.md"
      />,
    )
    expect(container.querySelector('script')).not.toBeInTheDocument()
    expect(container.innerHTML).not.toContain('<script>')
  })

  it('strips onerror/onclick event handler attributes', () => {
    const { container } = render(
      <BriefDocument
        markdown={'<img src="x" onerror="window.__pwned=true">'}
        contextFile="ctx.md"
      />,
    )
    const img = container.querySelector('img')
    expect(img).not.toBeNull()
    expect(img?.getAttribute('onerror')).toBeNull()
  })
})
