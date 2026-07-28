import { describe, expect, it } from 'vitest'
import { renderMarkdown, unwrapMarkdownFence } from './markdown'

describe('unwrapMarkdownFence', () => {
  it('unwraps a ```markdown fenced block into real markdown', () => {
    const wrapped = '前言:\n\n```markdown\n# 文档标题\n\n- 一\n- 二\n```\n'
    const out = unwrapMarkdownFence(wrapped)
    expect(out).toContain('# 文档标题')
    expect(out).not.toContain('```markdown')
  })

  it('also unwraps ```md', () => {
    expect(unwrapMarkdownFence('```md\n# H\n```')).toContain('# H')
  })

  it('leaves real code fences (e.g. ```bash) untouched', () => {
    const src = '```bash\ngit worktree list\n```'
    expect(unwrapMarkdownFence(src)).toBe(src)
  })
})

describe('renderMarkdown', () => {
  it('renders a markdown-fence-wrapped document as formatted markdown, not a code block', () => {
    const wrapped = '导语\n\n```markdown\n# 上下文文档\n\n## 相关文件\n\n- a\n```\n'
    const html = renderMarkdown(wrapped)
    expect(html).toContain('<h1')
    expect(html).toContain('<h2')
    expect(html).toContain('<li>a</li>')
    // 不应把整份文档塞进一个 <pre><code>
    expect(html).not.toMatch(/<pre><code[^>]*># 上下文文档/)
  })

  it('syntax-highlights genuine code blocks (hljs classes)', () => {
    const html = renderMarkdown('```bash\ngit worktree remove path\n```')
    expect(html).toContain('hljs')
  })
})
