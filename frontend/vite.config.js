import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

// In development, Vite forwards /api/* to FastAPI, so the browser sees a single
// origin. (The backend's CORS config still allows :5173 for direct calls.)
export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
    proxy: {
      "/api": "http://127.0.0.1:8000",
    },
  },
});
