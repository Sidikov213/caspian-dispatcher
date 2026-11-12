import type { NextConfig } from "next";

/** Статический экспорт для Caddy на `/`. Локально `next dev` тоже работает. */
const nextConfig: NextConfig = {
  output: "export",
  images: { unoptimized: true },
  turbopack: {
    // С адресом API заглушки не нужны: модуль с файлами src/mocks подменяется пустышкой.
    resolveAlias: process.env.NEXT_PUBLIC_API_URL ? { "./mockApi": "./src/lib/mockApi.off.ts" } : {},
    rules: {
      "*.css": {
        loaders: ["@tailwindcss/turbopack"],
        as: "*.css",
      },
    },
  },
};

export default nextConfig;
