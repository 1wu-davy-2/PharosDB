import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

// dev: frontend http://localhost:17000  backend http://localhost:17080
export default defineConfig({
  plugins: [react()],
  server: {
    port: 17000,
    proxy: {
      "/api": {
        target: "http://127.0.0.1:17080",
        changeOrigin: true,
      },
    },
  },
});
