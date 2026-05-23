import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  // Static export → out/ uploaded to GCS bucket fronted by Cloud CDN.
  // See infra/cdn.ts.
  output: "export",
};

export default nextConfig;
