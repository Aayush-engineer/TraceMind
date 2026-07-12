import { defineConfig } from "vite"
import react from "@vitejs/plugin-react"

export default defineConfig(({ mode }) => ({
  plugins: [react()],

  // Dev server proxy — only active when running `npm run dev` locally
  server: mode === "development" ? {
    port: 3000,
    proxy: {
      "/api": {
        target: "http://localhost:8000",
        changeOrigin: true,
      },
      "/ws": {
        target: "ws://localhost:8000",
        ws: true,
      },
    },
  } : {},

  build: {
    // Increase warning threshold — we intentionally split vendor chunks
    chunkSizeWarningLimit: 700,
    // Target modern browsers — smaller output, no IE11 polyfills
    target: "es2020",
    rollupOptions: {
      output: {
        manualChunks(id) {
          if (
            id.includes("react") ||
            id.includes("react-dom") ||
            id.includes("react-router-dom")
          ) {
            return "vendor-react";
          }

          if (id.includes("recharts")) {
            return "vendor-charts";
          }
        },
      },
    },
  },

  // Pre-bundle for faster cold-start in local dev
  optimizeDeps: {
    include: ["react", "react-dom", "react-router-dom", "recharts"],
  },
}))