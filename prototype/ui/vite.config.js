import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

// Dev server. When the FastAPI backend runs on :8000, set VITE_API_BASE in .env.local
// (see README). The proxy below lets VITE_API_BASE=/ work without CORS.
export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
    proxy: {
      "/api": { target: "http://localhost:8000", changeOrigin: true },
    },
  },
});
