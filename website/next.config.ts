import type { NextConfig } from "next";

/** Статический экспорт для Caddy на `/`. Локально `next dev` тоже работает. */
const nextConfig: NextConfig = {
  output: "export",
  images: { unoptimized: true },
  turbopack: {
    rules: {
      "*.css": {
        loaders: ["@tailwindcss/turbopack"],
        as: "*.css",
      },
    },
  },
};

export default nextConfig;
