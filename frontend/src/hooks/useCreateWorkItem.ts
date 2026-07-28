import { useMutation, useQueryClient } from '@tanstack/react-query'
import { useNavigate } from 'react-router-dom'
import { createWorkItem } from '../api/client'

export function useCreateWorkItem(projectId: string | undefined) {
  const queryClient = useQueryClient()
  const navigate = useNavigate()

  return useMutation({
    mutationFn: ({ goal, autonomyEnabled }: { goal: string; autonomyEnabled: boolean }) =>
      createWorkItem(projectId as string, goal, autonomyEnabled),
    onSuccess: async ({ id }) => {
      await queryClient.invalidateQueries({ queryKey: ['project', projectId] })
      navigate(`/projects/${projectId}/workitems/${id}`)
    },
  })
}
