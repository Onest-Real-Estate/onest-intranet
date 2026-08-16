import path from "node:path";

import { defineConfig } from "vitest/config";

export default defineConfig({
  resolve: {
    alias: {
      "@": path.resolve(import.meta.dirname, "frontend"),
    },
  },
  test: {
    environment: "node",
    include: ["frontend/**/*.test.{ts,tsx}"],
  },
});
