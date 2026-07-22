import { useQuery } from '@tanstack/react-query'
import { getProjects } from '../api/client'

export function useProjects() {
  return useQuery({
    queryKey: ['projects'],
    queryFn: getProjects,
  })
}
