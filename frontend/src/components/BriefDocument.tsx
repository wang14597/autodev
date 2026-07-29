import DOMPurify from 'dompurify'
import 'highlight.js/styles/github.css'
import { useMemo } from 'react'
import { renderMarkdown } from '../lib/markdown'
import styles from './BriefDocument.module.css'

/**
 * Renders a stage's Markdown document (context brief, design doc, ...). Markdown
 * is unwrapped (strip the model's outer ```markdown fence), parsed with GFM +
 * syntax highlighting, then sanitized before being handed to the DOM — never
 * trust model/user text.
 */
export function BriefDocument({
  title = '上下文简报',
  markdown,
  path,
}: {
  title?: string
  markdown: string
  path: string
}) {
  const html = useMemo(() => {
    // ADD_ATTR keeps hljs' <span class> highlighting through sanitization.
    return DOMPurify.sanitize(renderMarkdown(markdown), { ADD_ATTR: ['class'] })
  }, [markdown])

  return (
    // 原生 <details>：点击标题栏折叠/展开(默认展开),无障碍、零额外状态。
    <details className={styles.wrapper} aria-label={title} open>
      <summary className={styles.caption}>
        <span className={styles.chevron} aria-hidden="true" />
        <span className={styles.captionTitle}>{title}</span>
        <span className={styles.captionPath}>{path}</span>
      </summary>
      {/* sanitized via DOMPurify above */}
      <div className={styles.body} dangerouslySetInnerHTML={{ __html: html }} />
    </details>
  )
}
