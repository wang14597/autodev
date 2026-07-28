import DOMPurify from 'dompurify'
import 'highlight.js/styles/github.css'
import { useMemo } from 'react'
import { renderMarkdown } from '../lib/markdown'
import styles from './BriefDocument.module.css'

/**
 * Renders the CONTEXT stage's Markdown brief. Markdown is unwrapped (strip the
 * model's outer ```markdown fence), parsed with GFM + syntax highlighting, then
 * sanitized before being handed to the DOM — never trust model/user text.
 */
export function BriefDocument({
  markdown,
  contextFile,
}: {
  markdown: string
  contextFile: string
}) {
  const html = useMemo(() => {
    // ADD_ATTR keeps hljs' <span class> highlighting through sanitization.
    return DOMPurify.sanitize(renderMarkdown(markdown), { ADD_ATTR: ['class'] })
  }, [markdown])

  return (
    // 原生 <details>：点击标题栏折叠/展开(默认展开),无障碍、零额外状态。
    <details className={styles.wrapper} aria-label="上下文简报" open>
      <summary className={styles.caption}>
        <span className={styles.chevron} aria-hidden="true" />
        <span className={styles.captionTitle}>上下文简报</span>
        <span className={styles.captionPath}>{contextFile}</span>
      </summary>
      {/* sanitized via DOMPurify above */}
      <div className={styles.body} dangerouslySetInnerHTML={{ __html: html }} />
    </details>
  )
}
