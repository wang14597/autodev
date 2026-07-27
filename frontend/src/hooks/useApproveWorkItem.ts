import { useMutation, useQueryClient } from '@tanstack/react-query'
import { approveWorkItem } from '../api/client'

export function useApproveWorkItem(id: string | undefined) {
  const queryClient = useQueryClient()

  return useMutation({
    mutationFn: (approved: boolean) => approveWorkItem(id as string, approved),
    onSuccess: async () => {
      await queryClient.invalidateQueries({ queryKey: ['workitem', id] })
    },
  })
}
