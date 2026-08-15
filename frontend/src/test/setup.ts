import "@testing-library/jest-dom/vitest";

class ResizeObserverMock {
  observe() {}
  unobserve() {}
  disconnect() {}
}
// @ts-expect-error jsdom doesn't implement ResizeObserver
global.ResizeObserver = ResizeObserverMock;
