/** @type {import('next').NextConfig} */
const nextConfig = {
  reactStrictMode: true,
  output: 'standalone',
  // Keep the deployment layout stable regardless of the build workspace.
  outputFileTracingRoot: __dirname,
};

module.exports = nextConfig;

