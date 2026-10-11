/** @type {import('next').NextConfig} */
const nextConfig = {
  reactStrictMode: true,
  // Export estático (projmap/ui/out) servido pelo FastAPI do mestre: o mestre
  // roda nativo no Windows sem Node em produção, e o mesmo build vira o app
  // Android via Capacitor (F6). Decisão D2 em docs/projmap/PLANO.md.
  output: "export",
  // /sensor/ vira sensor/index.html: o StaticFiles do FastAPI serve sem regra extra.
  trailingSlash: true,
  images: { unoptimized: true },
};

export default nextConfig;
