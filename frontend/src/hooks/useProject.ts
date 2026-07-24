import { useQuery } from '@tanstack/react-query'
import { getProject } from '../api/client'
import type { ProjectDetail } from '../api/types'
import { isRunning } from '../lib/workitem'

// 项目详情轮询：只要其下任一工作项在运行(INTAKE/TRIAGE/CONTEXT)就每 3s 刷新，
// 让工作项徽标实时推进；全部静止后停止轮询。
export function projectRefetchInterval(detail: ProjectDetail | undefined): number | false {
  if (detail && detail.workitems.some((item) => isRunning(item.state))) return 3000
  return false
}

export function useProject(id: string | undefined) {
  return useQuery<ProjectDetail>({
    queryKey: ['project', id],
    queryFn: () => getProject(id as string),
    enabled: Boolean(id),
    refetchInterval: (query) => projectRefetchInterval(query.state.data),
  })
}
