import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  // Static export → out/ uploaded to GCS bucket fronted by Cloud CDN.
  // See infra/cdn.ts.
  output: "export",
  // Required for static export — Next can't run its image optimizer at
  // request time. Signed GCS URLs are passed through as-is.
  images: { unoptimized: true },
  experimental: {
    optimizePackageImports: ["@phosphor-icons/react"],
  },
};

export default nextConfig;
