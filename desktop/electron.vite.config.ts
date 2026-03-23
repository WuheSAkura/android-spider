import { defineConfig } from "electron-vite";
import react from "@vitejs/plugin-react";
import { resolve } from "path";

export default defineConfig({
  main: {
    build: {
      outDir: "out/main",
    },
  },
  preload: {
    build: {
      outDir: "out/preload",
    },
  },
  renderer: {
    resolve: {
      alias: {
        "@": resolve(__dirname, "src/renderer/src"),
      },
    },
    plugins: [react()],
    build: {
      outDir: "out/renderer",
    },
  },
});
