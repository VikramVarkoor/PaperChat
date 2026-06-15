/** @type {import('next').NextConfig} */

// In development: BACKEND_URL is not set, so we fall back to localhost:8000
// In production (Vercel): set BACKEND_URL to your Render backend URL
// e.g. https://paperchat-api.onrender.com
const BACKEND_URL = process.env.BACKEND_URL || "http://localhost:8000";

const nextConfig = {
  async rewrites() {
    return [
      {
        source: "/api/py/:path*",
        destination: `${BACKEND_URL}/:path*`,
      },
    ];
  },
};

module.exports = nextConfig;
