import path from "node:path";
import { fileURLToPath } from "node:url";
const root = path.dirname(fileURLToPath(import.meta.url));
export default {
  reactStrictMode: true,
  outputFileTracingRoot: path.join(root, ".."),
  async rewrites() {
    return [
      {
        source: "/api/sales/:path*",
        destination: `${process.env.BACKEND_URL || "http://127.0.0.1:8001"}/api/:path*`,
      },
    ];
  },
};
