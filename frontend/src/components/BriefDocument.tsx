import DOMPurify from 'dompurify'
import { marked } from 'marked'
import { useMemo } from 'react'
import styles from './BriefDocument.module.css'

/**
 * Renders the CONTEXT stage's Markdown brief. Markdown is parsed synchronously
 * then sanitized before being handed to the DOM — never trust model/user text.
 */
export function BriefDocument({
  markdown,
  contextFile,
}: {
  markdown: string
  contextFile: string
}) {
  const html = useMemo(() => {
    const rawHtml = marked.parse(markdown, { async: false })
    return DOMPurify.sanitize(rawHtml)
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
