import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

// In Docker Compose the API is reachable at http://api:8000 (service name),
// NOT localhost — localhost inside the web container is the web container
// itself. docker-compose.yml sets API_PROXY_TARGET=http://api:8000.
// For bare-metal dev (uvicorn on the host) the default localhost works.
const apiTarget = process.env.API_PROXY_TARGET || "http://localhost:8000";
const wsTarget = apiTarget.replace(/^http/, "ws");

export default defineConfig({
  plugins: [react()],
  server: {
    host: true, // listen on 0.0.0.0 so the container port is reachable
    // File watching across a Docker bind mount needs polling on many hosts.
    watch: { usePolling: true },
    proxy: {
      "/api": { target: apiTarget, changeOrigin: true },
      "/ws": { target: wsTarget, ws: true },
    },
  },
});
