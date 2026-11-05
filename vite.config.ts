import { defineConfig } from "vite";
import vue from "@vitejs/plugin-vue";
import { fileURLToPath, URL } from "node:url";
export default defineConfig({
  plugins: [vue()],
  base: "/static/ui/",
  build: {
    outDir: "static/ui",
    emptyOutDir: true,
    manifest: true,
    sourcemap: false,
    rollupOptions: {
      input: fileURLToPath(new URL("./frontend/main.ts", import.meta.url)),
    },
  },
});
