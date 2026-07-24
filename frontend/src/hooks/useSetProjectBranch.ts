import { useMutation, useQueryClient } from '@tanstack/react-query'
import { setProjectBranch } from '../api/client'

export function useSetProjectBranch(projectId: string | undefined) {
  const queryClient = useQueryClient()

  return useMutation({
    mutationFn: (branch: string) => setProjectBranch(projectId as string, branch),
    onSuccess: async () => {
      await queryClient.invalidateQueries({ queryKey: ['project', projectId] })
      await queryClient.invalidateQueries({ queryKey: ['projects'] })
    },
  })
}
