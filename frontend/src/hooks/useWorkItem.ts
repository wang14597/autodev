import { useQuery } from '@tanstack/react-query'
import { getWorkItem } from '../api/client'
import type { WorkItemDetail, WorkItemState } from '../api/types'
import { isRunning } from '../lib/workitem'

/** Poll every 2s while the bounded driver is running; stop once the WorkItem rests. */
export const POLL_INTERVAL_MS = 2000

/**
 * Standalone refetch-interval selector — exported so it can be unit-tested
 * without mounting a query. Mirrors TanStack Query's `refetchInterval` shape:
 * a truthy number keeps polling, `false` stops.
 */
export function pollingInterval(state: WorkItemState | undefined): number | false {
  if (!state) return false
  return isRunning(state) ? POLL_INTERVAL_MS : false
}

export function useWorkItem(id: string | undefined) {
  return useQuery<WorkItemDetail>({
    queryKey: ['workitem', id],
    queryFn: () => getWorkItem(id as string),
    enabled: Boolean(id),
    refetchInterval: (query) => pollingInterval(query.state.data?.state),
  })
}
