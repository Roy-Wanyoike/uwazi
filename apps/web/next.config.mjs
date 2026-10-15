/** @type {import('next').NextConfig} */
const nextConfig = {
  reactStrictMode: true,
  // Allow the dev server to proxy /api to the FastAPI backend at localhost:8000
  async rewrites() {
    return [
      {
        source: '/api/:path*',
        destination: `${process.env.BIDBOX_API_URL ?? 'http://localhost:8000'}/api/:path*`,
      },
    ];
  },
};

export default nextConfig;
