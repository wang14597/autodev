import { useQuery } from '@tanstack/react-query'
import { getProjectBranches } from '../api/client'

export function useProjectBranches(id: string | undefined) {
  return useQuery<string[]>({
    queryKey: ['project', id, 'branches'],
    queryFn: () => getProjectBranches(id as string),
    enabled: Boolean(id),
  })
}
