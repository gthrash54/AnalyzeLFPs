import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";
import tailwindcss from "@tailwindcss/vite";

export default defineConfig({
  plugins: [react(), tailwindcss()],
  server: {
    port: 5173,
    // The API binds to localhost only and has no auth. Proxying keeps the
    // browser talking to one origin, so there is no CORS surface to widen.
    // No rewrite: the API is mounted at /api on the server too, so the path
    // that works here is the path that works in a deployment.
    proxy: { "/api": { target: "http://127.0.0.1:8000" } },
  },
});
