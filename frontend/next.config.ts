import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  // Standalone output for the Docker runner stage (ships a minimal server.js)
  output: "standalone",
};

export default nextConfig;
