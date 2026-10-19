import { defineConfig } from "vitest/config";
import path from "node:path";

const isCi = Boolean(
  process.env.CI && process.env.CI !== "false" && process.env.CI !== "0",
);

export default defineConfig({
  test: {
    environment: "node",
    include: ["tests/**/*.test.ts"],
    coverage: {
      enabled: false,
    },
    // `npm test` keeps watch mode on a local TTY. CI must exit after one run
    // even when stdin is a TTY. `npm run test:run` stays `vitest run`.
    ...(isCi ? { watch: false } : {}),
  },
  resolve: {
    alias: {
      "@": path.resolve(__dirname, "src"),
    },
  },
});
