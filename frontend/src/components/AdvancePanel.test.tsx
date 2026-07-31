import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, it, vi } from 'vitest'
import { AdvancePanel } from './AdvancePanel'

describe('AdvancePanel', () => {
  it('advance 态渲染可点按钮并显示下一阶段', async () => {
    const onAdvance = vi.fn()
    render(
      <AdvancePanel
        nextAction="advance"
        nextStage="方案"
        onAdvance={onAdvance}
        isPending={false}
      />,
    )

    const button = screen.getByTestId('advance-button')
    expect(button).toBeEnabled()
    expect(screen.getByText(/方案/)).toBeInTheDocument()

    await userEvent.click(button)
    expect(onAdvance).toHaveBeenCalledOnce()
  })

  it('blocked 态按钮禁用并说明尚未建设', () => {
    render(
      <AdvancePanel nextAction="blocked" nextStage="评审" onAdvance={vi.fn()} isPending={false} />,
    )

    expect(screen.getByTestId('advance-button')).toBeDisabled()
    expect(screen.getByText(/尚未建设/)).toBeInTheDocument()
  })

  it('isPending 时按钮禁用', () => {
    render(
      <AdvancePanel nextAction="advance" nextStage="方案" onAdvance={vi.fn()} isPending={true} />,
    )
    expect(screen.getByTestId('advance-button')).toBeDisabled()
  })

  it('decide / none 态不渲染任何东西（交给人审面板或无操作）', () => {
    const { container: a } = render(
      <AdvancePanel nextAction="decide" nextStage={null} onAdvance={vi.fn()} isPending={false} />,
    )
    expect(a).toBeEmptyDOMElement()

    const { container: b } = render(
      <AdvancePanel nextAction="none" nextStage={null} onAdvance={vi.fn()} isPending={false} />,
    )
    expect(b).toBeEmptyDOMElement()
  })
})
