import type { NextConfig } from 'next';

const nextConfig: NextConfig = {
  output: 'export',
  basePath: '/radar',
  trailingSlash: true,
  images: { unoptimized: true },
};

export default nextConfig;
