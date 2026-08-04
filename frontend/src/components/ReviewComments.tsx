import styles from './ReviewComments.module.css'

interface ReviewCommentsProps {
  comments: string[]
  /** 本轮评审是否通过。为 false 时额外给出打回说明，避免只看到一串评论却不知发生了什么。 */
  approved?: boolean
}

/** 评审意见列表。前缀（`- blocking:` / `- suggestion:`）由后端原样保留，此处据其分类着色。 */
export function ReviewComments({ comments, approved }: ReviewCommentsProps) {
  if (comments.length === 0) return null
  return (
    <>
      {approved === false && (
        <p className={styles.rejectedHint} data-testid="review-rejected-hint">
          评审未通过，已退回重新设计。
        </p>
      )}
      <ul className={styles.list} data-testid="review-comments">
        {comments.map((c, i) => (
          <li key={`${i}-${c}`} data-kind={c.startsWith('- blocking:') ? 'blocking' : 'suggestion'}>
            {c.replace(/^- (blocking|suggestion):\s*/, '')}
          </li>
        ))}
      </ul>
    </>
  )
}
