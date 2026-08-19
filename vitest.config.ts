import path from "node:path";

import { defineConfig } from "vitest/config";

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
  },
});
