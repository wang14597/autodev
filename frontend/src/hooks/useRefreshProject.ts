import { useMutation, useQueryClient } from '@tanstack/react-query'
import { refreshProject } from '../api/client'

export function useRefreshProject(projectId: string | undefined) {
  const queryClient = useQueryClient()

  return useMutation({
    mutationFn: () => refreshProject(projectId as string),
    onSuccess: async () => {
      await queryClient.invalidateQueries({ queryKey: ['project', projectId] })
      await queryClient.invalidateQueries({ queryKey: ['projects'] })
    },
  })
}
