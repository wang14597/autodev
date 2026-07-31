import { useMutation, useQueryClient } from '@tanstack/react-query'
import { advanceWorkItem } from '../api/client'

export function useAdvanceWorkItem(id: string | undefined) {
  const queryClient = useQueryClient()

  return useMutation({
    mutationFn: () => advanceWorkItem(id as string),
    onSuccess: async () => {
      await queryClient.invalidateQueries({ queryKey: ['workitem', id] })
    },
  })
}
