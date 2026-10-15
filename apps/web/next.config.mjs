/** @type {import('next').NextConfig} */

// On Vercel: the vercel.json `services` + `rewrites` handle the
// /api/* → api-service routing. Do NOT proxy here — it would conflict.
// On local dev (`next dev`): proxy /api/* to the FastAPI server at
// localhost:8000 so the browser can call relative URLs.
const isVercel = !!process.env.VERCEL;

const nextConfig = {
  reactStrictMode: true,
  ...(isVercel
    ? {}
    : {
        async rewrites() {
          return [
            {
              source: "/api/:path*",
              destination: `${
                process.env.UWAZI_API_URL ?? "http://localhost:8000"
              }/api/:path*`,
            },
          ];
        },
      }),
};

export default nextConfig;
