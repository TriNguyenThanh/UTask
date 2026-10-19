import path from "node:path";

import tailwindcss from "@tailwindcss/vite";
import react from "@vitejs/plugin-react";
import { loadEnv } from "vite";
import { defineConfig } from "vitest/config";

const DEFAULT_API_PROXY_TARGET = "https://utask-api.u-code.dev";

export default defineConfig(({ mode }) => {
  const env = loadEnv(mode, process.cwd(), "");
  const target = env.VITE_API_PROXY_TARGET || DEFAULT_API_PROXY_TARGET;

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
          // Cookie refresh/CSRF phải gắn vào origin của dev server, không phải domain của backend.
          cookieDomainRewrite: "",
          configure(proxy) {
            // Gateway chuyển HTTPS sang Django dưới dạng HTTP nên Django coi `Origin` https là origin lạ
            // và trả 403 khi kiểm CSRF (refresh, logout-all). Không có `Origin`/`Referer` thì Django chỉ
            // kiểm token CSRF. Chỉ dùng cho dev; production cần backend cấu hình CSRF_TRUSTED_ORIGINS.
            proxy.on("proxyReq", (proxyReq) => {
              proxyReq.removeHeader("origin");
              proxyReq.removeHeader("referer");
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
