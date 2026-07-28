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
    <section className={styles.wrapper} aria-label="上下文简报">
      <header className={styles.caption}>
        <span className={styles.captionTitle}>上下文简报</span>
        <span className={styles.captionPath}>{contextFile}</span>
      </header>
      {/* sanitized via DOMPurify above */}
      <div className={styles.body} dangerouslySetInnerHTML={{ __html: html }} />
    </section>
  )
}
