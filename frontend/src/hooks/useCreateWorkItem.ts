import { useMutation, useQueryClient } from '@tanstack/react-query'
import { useNavigate } from 'react-router-dom'
import { createWorkItem } from '../api/client'

export function useCreateWorkItem() {
  const queryClient = useQueryClient()
  const navigate = useNavigate()

  return useMutation({
    mutationFn: ({ goal, repo }: { goal: string; repo: string }) => createWorkItem(goal, repo),
    onSuccess: async ({ id }) => {
      await queryClient.invalidateQueries({ queryKey: ['workitems'] })
      navigate(`/workitems/${id}`)
    },
  })
}
