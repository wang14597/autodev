import { useState } from 'react'
import type { FormEvent } from 'react'
import { ApiError } from '../api/client'
import { useCreateWorkItem } from '../hooks/useCreateWorkItem'
import styles from './NewWorkItemForm.module.css'

export function NewWorkItemForm({ projectId }: { projectId: string }) {
  const mutation = useCreateWorkItem(projectId)
  const [goal, setGoal] = useState('')
  const [validationError, setValidationError] = useState<string | null>(null)

  function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    if (goal.trim() === '') {
      setValidationError('需求不能为空。')
      return
    }
    setValidationError(null)
    mutation.mutate(goal.trim())
  }

  const serverError =
    mutation.error instanceof ApiError ? mutation.error.detail : mutation.error?.message

  return (
    <form className={styles.form} onSubmit={handleSubmit} noValidate>
      <div className={styles.field}>
        <label className={styles.label} htmlFor="workitem-goal">
          需求
        </label>
        <textarea
          id="workitem-goal"
          className={styles.textarea}
          value={goal}
          onChange={(e) => setGoal(e.target.value)}
          placeholder="描述这次要做的需求…"
          disabled={mutation.isPending}
        />
      </div>

      {validationError && <p className={styles.error}>{validationError}</p>}
      {!validationError && serverError && <p className={styles.error}>{serverError}</p>}

      <button type="submit" className={styles.submit} disabled={mutation.isPending}>
        {mutation.isPending ? '创建中…' : '创建工作项'}
      </button>
    </form>
  )
}
