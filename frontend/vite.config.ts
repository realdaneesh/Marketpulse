import { defineConfig, loadEnv } from "vite";
import react from "@vitejs/plugin-react";
import tailwindcss from "@tailwindcss/vite";
import type { InlineConfig } from "vitest/node";

export default defineConfig(({ mode }) => {
  const env = loadEnv(mode, process.cwd(), "");
  const proxy = {
    target: env.MARKETPULSE_API_TARGET || "http://127.0.0.1:8000",
    changeOrigin: true,
  };
  return {
    plugins: [react(), tailwindcss()],
    server: {
      port: 5173,
      strictPort: true,
      proxy: { "/api": proxy, "/health": proxy },
    },
    preview: {
      port: 4173,
      strictPort: true,
      proxy: { "/api": proxy, "/health": proxy },
    },
    test: {
      include: ["src/**/*.test.{ts,tsx}"],
      environment: "jsdom",
      setupFiles: ["./src/test/setup.ts"],
      restoreMocks: true,
    } satisfies InlineConfig,
  };
});
