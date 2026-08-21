import path from "node:path";
import process from "node:process";

import { defineConfig } from "vitest/config";

// Node 25+ turns on a process-level Web Storage API that leaves jsdom's
// `window.localStorage` undefined. CI stays on Node 22, which has no flag.
const disableNodeWebstorage =
  Number.parseInt(process.versions.node, 10) >= 25 ? ["--no-webstorage"] : [];

export default defineConfig({
  resolve: {
    alias: {
      "@": path.resolve(import.meta.dirname, "frontend"),
    },
  },
  test: {
    environment: "jsdom",
    include: ["frontend/**/*.test.{ts,tsx}"],
    setupFiles: ["frontend/test/setup.ts"],
    execArgv: disableNodeWebstorage,
    // jsdom + Radix under parallel load routinely exceeds Vitest's 5s default.
    testTimeout: 15_000,
  },
});
