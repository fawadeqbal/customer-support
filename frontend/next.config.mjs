/**
 * Local development: requests to /api/... are forwarded to Flask, so the
 * frontend never needs the Flask URL and there are no CORS problems.
 * Production: nginx sends /api/... straight to the rag-api container.
 */
const nextConfig = {
  output: "standalone", // small self-contained server for the Docker image
  compress: false,      // don't buffer streamed answers in local dev (nginx compresses in production)
  async rewrites() {
    const api = process.env.API_URL || "http://127.0.0.1:5000";
    return [{ source: "/api/:path*", destination: `${api}/api/:path*` }];
  },
  experimental: { proxyTimeout: 300000 }, // local models on a CPU can take a while
};

export default nextConfig;
