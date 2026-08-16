import path from "node:path";
import tailwindcss from "@tailwindcss/vite";
import react from "@vitejs/plugin-react";
import { defineConfig } from "vite";

const rootDir = import.meta.dirname;

export default defineConfig({
  plugins: [react(), tailwindcss()],
  // The frontend source lives directly in frontend/. django-vite's dev URL is
  // /static/main.tsx, which resolves against this root.
  root: path.resolve(rootDir, "frontend"),
  // Match Django's STATIC_URL.
  base: "/static/",
  resolve: {
    alias: {
      "@": path.resolve(rootDir, "frontend"),
    },
  },
  build: {
    // django-vite reads this manifest in production mode.
    manifest: "manifest.json",
    // Django serves this via STATICFILES_DIRS.
    outDir: path.resolve(rootDir, "assets"),
    emptyOutDir: true,
    rollupOptions: {
      input: {
        main: path.resolve(rootDir, "frontend/main.tsx"),
      },
    },
  },
  server: {
    port: 5173,
    strictPort: true,
    host: "localhost",
  },
});
