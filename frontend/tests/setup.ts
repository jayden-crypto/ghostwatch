import "@testing-library/jest-dom/vitest";

import { cleanup } from "@testing-library/react";
import { afterEach } from "vitest";

// jsdom does not lay anything out, so it has no scrolling.
Element.prototype.scrollIntoView ??= () => undefined;
// Nor sizes: Radix's checkbox observes its own, and nothing ever resizes here.
globalThis.ResizeObserver ??= class {
  observe() {}
  unobserve() {}
  disconnect() {}
};

afterEach(cleanup);
