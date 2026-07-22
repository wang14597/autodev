import { useQuery } from '@tanstack/react-query'
import { listWorkItems } from '../api/client'

export function useWorkItems() {
  return useQuery({
    queryKey: ['workitems'],
    queryFn: listWorkItems,
  })
}
