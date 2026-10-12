import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

// In development, /api requests are forwarded to the Flask server,
// so the browser sees a single origin and no CORS setup is needed.
export default defineConfig({
  plugins: [react()],
  server: { proxy: { "/api": "http://127.0.0.1:5000" } },
});
