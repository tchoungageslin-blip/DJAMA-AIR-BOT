/** @type {import('next').NextConfig} */
const nextConfig = {
  async rewrites() {
    return [
      {
        source: "/api/webhook",
        destination: "/api/index",
      },
      {
        source: "/api/bot/:path*",
        destination: "/api/index",
      },
      {
        source: "/api/dashboard/:path*",
        destination: "/api/index",
      },
    ];
  },
};

export default nextConfig;
