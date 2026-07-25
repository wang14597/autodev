import '@testing-library/jest-dom/vitest'

// antd (via @rc-component/resize-observer, used by Select's dropdown positioning)
// calls `ResizeObserver`, which jsdom does not implement. Stub a minimal version so
// antd components mount without throwing in tests.
if (typeof window !== 'undefined' && !window.ResizeObserver) {
  class ResizeObserverStub {
    observe() {}
    unobserve() {}
    disconnect() {}
  }
  window.ResizeObserver = ResizeObserverStub as unknown as typeof ResizeObserver
}
