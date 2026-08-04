import { render, screen } from '@testing-library/react'
import { describe, expect, it } from 'vitest'
import { ReviewComments } from './ReviewComments'

describe('ReviewComments', () => {
  it('renders nothing when there are no comments', () => {
    const { container } = render(<ReviewComments comments={[]} />)
    expect(container.firstChild).toBeNull()
  })

  it('renders each comment as a list item', () => {
    render(<ReviewComments comments={['- blocking: 方向不对', '- suggestion: 补测试']} />)
    expect(screen.getByText(/方向不对/)).toBeInTheDocument()
    expect(screen.getByText(/补测试/)).toBeInTheDocument()
  })

  it('marks blocking and suggestion items differently so 拦路的一眼可辨', () => {
    const { container } = render(
      <ReviewComments comments={['- blocking: 方向不对', '- suggestion: 补测试']} />,
    )
    const kinds = [...container.querySelectorAll('li')].map((li) => li.dataset.kind)
    expect(kinds).toEqual(['blocking', 'suggestion'])
  })

  it('当 approved 为 false 时给出「评审未通过，已退回重新设计」的说明文案', () => {
    render(<ReviewComments comments={['- blocking: 需求自相矛盾']} approved={false} />)
    expect(screen.getByText(/评审未通过，已退回重新设计/)).toBeInTheDocument()
  })

  it('当 approved 为 true（或未传入）时不出现打回说明文案', () => {
    render(<ReviewComments comments={['- suggestion: 补测试']} approved={true} />)
    expect(screen.queryByText(/评审未通过/)).not.toBeInTheDocument()
  })

  it('重复文本的评论各自渲染为独立列表项（key 不再用评论原文，避免同文案碰撞丢项）', () => {
    render(<ReviewComments comments={['- suggestion: 同样的话', '- suggestion: 同样的话']} />)
    expect(screen.getAllByText('同样的话')).toHaveLength(2)
  })
})
