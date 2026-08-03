import styles from './ReviewComments.module.css'

/** 评审意见列表。前缀（`- blocking:` / `- suggestion:`）由后端原样保留，此处据其分类着色。 */
export function ReviewComments({ comments }: { comments: string[] }) {
  if (comments.length === 0) return null
  return (
    <ul className={styles.list} data-testid="review-comments">
      {comments.map((c) => (
        <li key={c} data-kind={c.startsWith('- blocking:') ? 'blocking' : 'suggestion'}>
          {c.replace(/^- (blocking|suggestion):\s*/, '')}
        </li>
      ))}
    </ul>
  )
}
