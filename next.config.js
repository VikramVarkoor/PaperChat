/** @type {import('next').NextConfig} */

// next.config.js is the main configuration file for your Next.js app.
// It lives at the root of the project and gets read when you run `npm run dev` or `npm run build`.
// You can use it to configure things like:
//   - Environment variables
//   - Redirects / rewrites
//   - Image optimization settings
//   - Custom HTTP headers
// The one key thing we need here: proxy API calls to our Python backend.

const nextConfig = {
  // `rewrites` let us forward requests starting with /api/py/...
  // to our FastAPI backend running on localhost:8000.
  //
  // WHY do we need this?
  // Browsers block "cross-origin" requests by default (CORS policy).
  // If your Next.js app is on localhost:3000 and your FastAPI is on
  // localhost:8000, the browser sees them as different "origins" and
  // blocks the request unless the backend explicitly allows it.
  //
  // By using rewrites, the browser only ever talks to localhost:3000.
  // Next.js then secretly forwards the request to :8000 server-side.
  // No CORS issues, cleaner URLs, easy to swap backend URLs in production.
  async rewrites() {
    return [
      {
        source: "/api/py/:path*",
        destination: "http://localhost:8000/:path*",
      },
    ];
  },
};

module.exports = nextConfig;
