import { useState } from 'react'
import type { FormEvent } from 'react'
import { ApiError } from '../api/client'
import { useCreateProject } from '../hooks/useCreateProject'
import styles from './NewProjectForm.module.css'

export function NewProjectForm() {
  const mutation = useCreateProject()
  const [name, setName] = useState('')
  const [repo, setRepo] = useState('')
  const [validationError, setValidationError] = useState<string | null>(null)

  function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    if (name.trim() === '' || repo.trim() === '') {
      setValidationError('项目名和仓库都要填。')
      return
    }
    setValidationError(null)
    mutation.mutate({ name: name.trim(), repo: repo.trim() })
  }

  const serverError =
    mutation.error instanceof ApiError ? mutation.error.detail : mutation.error?.message

  return (
    <form className={styles.form} onSubmit={handleSubmit} noValidate>
      <div className={styles.field}>
        <label className={styles.label} htmlFor="project-name">
          项目名
        </label>
        <input
          id="project-name"
          className={styles.input}
          value={name}
          onChange={(e) => setName(e.target.value)}
          placeholder="给项目起个名字…"
          disabled={mutation.isPending}
        />
      </div>

      <div className={styles.field}>
        <label className={styles.label} htmlFor="project-repo">
          仓库地址或本地 git 路径
        </label>
        <input
          id="project-repo"
          className={styles.input}
          value={repo}
          onChange={(e) => setRepo(e.target.value)}
          placeholder="git 远程地址，或本地仓库目录路径"
          disabled={mutation.isPending}
        />
        <p className={styles.hint}>首次登记会做一次性 setup（探测默认分支），之后自动复用。</p>
      </div>

      {validationError && <p className={styles.error}>{validationError}</p>}
      {!validationError && serverError && <p className={styles.error}>{serverError}</p>}

      <button type="submit" className={styles.submit} disabled={mutation.isPending}>
        {mutation.isPending ? '创建中…' : '创建项目'}
      </button>
    </form>
  )
}
