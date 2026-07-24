import { useMutation, useQueryClient } from '@tanstack/react-query'
import { useNavigate } from 'react-router-dom'
import { createProject } from '../api/client'

export function useCreateProject() {
  const queryClient = useQueryClient()
  const navigate = useNavigate()

  return useMutation({
    mutationFn: ({ name, repo }: { name: string; repo: string }) => createProject(name, repo),
    onSuccess: async ({ id }) => {
      await queryClient.invalidateQueries({ queryKey: ['projects'] })
      navigate(`/projects/${id}`)
    },
  })
}
