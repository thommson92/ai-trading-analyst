import type { NextConfig } from 'next';

const nextConfig: NextConfig = {
  reactStrictMode: true,
  // Das Dashboard laeuft hinter einem Reverse Proxy (Doc 10, Paragraph 14).
  // Die Angabe verhindert, dass Next.js absolute URLs auf den internen
  // Containernamen erzeugt.
  poweredByHeader: false,
};

export default nextConfig;
