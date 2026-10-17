import type { NextConfig } from 'next';

const nextConfig: NextConfig = {
  // Every page depends on the signed-in user, so we keep the dynamic-by-default
  // model (no Cache Components).
  images: {
    remotePatterns: [
      { protocol: 'https', hostname: '**.supabase.co' },
      { protocol: 'https', hostname: '**.supabase.in' },
    ],
  },
  turbopack: {
    rules: {
      '*.css': {
        loaders: ['@tailwindcss/turbopack'],
        as: '*.css',
      },
    },
  },
};

export default nextConfig;
