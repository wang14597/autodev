import { useMutation, useQueryClient } from '@tanstack/react-query'
import { useNavigate } from 'react-router-dom'
import { createProject } from '../api/client'

export function useCreateProject() {
  const queryClient = useQueryClient()
  const navigate = useNavigate()

  return useMutation({
    mutationFn: ({ name, repo, branch }: { name: string; repo: string; branch: string }) =>
      createProject(name, repo, branch),
    onSuccess: async ({ id }) => {
      await queryClient.invalidateQueries({ queryKey: ['projects'] })
      navigate(`/projects/${id}`)
    },
  })
}
