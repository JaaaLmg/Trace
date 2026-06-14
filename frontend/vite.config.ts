import { defineConfig, loadEnv } from "vite";
import vue from "@vitejs/plugin-vue";

export default defineConfig(({ mode }) => {
  const env = loadEnv(mode, process.cwd(), "");
  const apiTarget = env.VITE_TRACE_API_PROXY_TARGET || "http://127.0.0.1:8000";

  return {
    plugins: [vue()],
    build: {
      rollupOptions: {
        input: {
          app: "index.html"
        }
      }
    },
    server: {
      port: 5173,
      strictPort: false,
      proxy: {
        "/api": {
          target: apiTarget,
          changeOrigin: true
        },
        "/healthz": {
          target: apiTarget,
          changeOrigin: true
        }
      }
    }
  };
});
