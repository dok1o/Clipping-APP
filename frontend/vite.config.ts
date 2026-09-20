import react from "@vitejs/plugin-react";
import { defineConfig } from "vite";

// Dev proxy: frontend calls relative /api and /health; vite forwards to the backend,
// so no CORS pain in local dev. In prod VITE_API_URL overrides the base.
export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
    proxy: {
      "/api": { target: "http://localhost:8000", changeOrigin: true },
      "/health": { target: "http://localhost:8000", changeOrigin: true },
    },
  },
});
