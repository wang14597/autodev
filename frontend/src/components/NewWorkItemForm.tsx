import { useId, useState } from 'react'
import type { FormEvent } from 'react'
import { ApiError } from '../api/client'
import { useCreateWorkItem } from '../hooks/useCreateWorkItem'
import { useProjects } from '../hooks/useProjects'
import styles from './NewWorkItemForm.module.css'

export function NewWorkItemForm() {
  const { data: projects } = useProjects()
  const mutation = useCreateWorkItem()
  const [goal, setGoal] = useState('')
  const [repo, setRepo] = useState('')
  const [validationError, setValidationError] = useState<string | null>(null)
  const datalistId = useId()

  function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    if (goal.trim() === '' || repo.trim() === '') {
      setValidationError('需求和项目都要填。')
      return
    }
    setValidationError(null)
    mutation.mutate({ goal: goal.trim(), repo: repo.trim() })
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

      <div className={styles.field}>
        <label className={styles.label} htmlFor="workitem-repo">
          项目
        </label>
        <input
          id="workitem-repo"
          className={styles.input}
          list={datalistId}
          value={repo}
          onChange={(e) => setRepo(e.target.value)}
          placeholder="项目名，或本地 git 仓库路径"
          disabled={mutation.isPending}
        />
        <datalist id={datalistId}>
          {(projects ?? []).map((project) => (
            <option key={project} value={project} />
          ))}
        </datalist>
        <p className={styles.hint}>填已登记项目名，或本地 git 仓库目录路径（会自动登记）。</p>
      </div>

      {validationError && <p className={styles.error}>{validationError}</p>}
      {!validationError && serverError && <p className={styles.error}>{serverError}</p>}

      <button type="submit" className={styles.submit} disabled={mutation.isPending}>
        {mutation.isPending ? '创建中…' : '创建工作项'}
      </button>
    </form>
  )
}
