import { useQuery } from '@tanstack/react-query'
import { listWorkItems } from '../api/client'
import type { WorkItemSummary } from '../api/types'
import { isRunning } from '../lib/workitem'

// 列表轮询：只要有任一工作项在运行(INTAKE/TRIAGE/CONTEXT)就每 3s 刷新，
// 让工作台上多个并行工作项的状态徽标实时推进；全部静止后停止轮询。
export function workItemsRefetchInterval(items: WorkItemSummary[] | undefined): number | false {
  if (items && items.some((it) => isRunning(it.state))) return 3000
  return false
}

export function useWorkItems() {
  return useQuery({
    queryKey: ['workitems'],
    queryFn: listWorkItems,
    refetchInterval: (query) => workItemsRefetchInterval(query.state.data),
  })
}
