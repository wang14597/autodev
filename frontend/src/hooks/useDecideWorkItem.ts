import { useMutation, useQueryClient } from '@tanstack/react-query'
import { decideWorkItem, type DecideAction } from '../api/client'

export function useDecideWorkItem(id: string | undefined) {
  const queryClient = useQueryClient()

  return useMutation({
    mutationFn: (action: DecideAction) => decideWorkItem(id as string, action),
    onSuccess: async () => {
      await queryClient.invalidateQueries({ queryKey: ['workitem', id] })
    },
  })
}
