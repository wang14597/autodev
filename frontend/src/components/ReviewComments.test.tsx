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
})
