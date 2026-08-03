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

  it('取值不认识时闭合，绝不摆出可点按钮', () => {
    // 后端版本不一致(旧后端不投影 next_action)时运行时就是 undefined ——
    // `request` 的 `as T` 不做校验，拦不住，所以这是真实可达的边界，不是假想。
    // 实测过:旧后端 + 新前端会渲染出一个可点的「推进下一步」+ 占位文案「下一阶段」。
    const unknown = undefined as unknown as 'advance'
    const { container } = render(
      <AdvancePanel nextAction={unknown} nextStage={null} onAdvance={vi.fn()} isPending={false} />,
    )
    expect(container).toBeEmptyDOMElement()
  })

  it('advance 但拿不到阶段名时闭合，不渲染占位文案', () => {
    const { container } = render(
      <AdvancePanel nextAction="advance" nextStage={null} onAdvance={vi.fn()} isPending={false} />,
    )

    expect(container).toBeEmptyDOMElement()
    expect(screen.queryByText(/下一阶段/)).not.toBeInTheDocument()
  })
})
