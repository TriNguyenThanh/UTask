import path from "node:path";

import tailwindcss from "@tailwindcss/vite";
import react from "@vitejs/plugin-react";
import { loadEnv } from "vite";
import { defineConfig } from "vitest/config";

const DEFAULT_API_PROXY_TARGET = "https://utask-api.u-code.dev";

export default defineConfig(({ mode }) => {
  const env = loadEnv(mode, process.cwd(), "");
  const target = env.VITE_API_PROXY_TARGET || DEFAULT_API_PROXY_TARGET;
  const targetOrigin = new URL(target).origin;

  return {
    plugins: [react(), tailwindcss()],
    resolve: {
      alias: {
        "@": path.resolve(__dirname, "./src"),
      },
    },
    server: {
      proxy: {
        // Gateway không bật CORS cho origin ngoài localhost nên trình duyệt phải gọi cùng origin.
        "/api": {
          target,
          changeOrigin: true,
          secure: true,
          configure(proxy) {
            // Django so `Origin` với `Host` khi kiểm CSRF; changeOrigin đổi `Host` nên phải đổi `Origin` theo.
            proxy.on("proxyReq", (proxyReq) => {
              if (proxyReq.getHeader("origin")) {
                proxyReq.setHeader("origin", targetOrigin);
              }
            });
          },
        },
      },
    },
    test: {
      environment: "jsdom",
      environmentOptions: { jsdom: { url: "http://localhost" } },
      setupFiles: ["./src/test/setup.ts"],
    },
  };
});
