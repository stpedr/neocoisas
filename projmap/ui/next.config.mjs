/** @type {import('next').NextConfig} */
const nextConfig = {
  reactStrictMode: true,
  // Export estático (projmap/ui/out) servido pelo FastAPI do mestre: o mestre
  // roda nativo no Windows sem Node em produção, e o mesmo build vira o app
  // Android via Capacitor (F6). Decisão D2 em docs/projmap/PLANO.md.
  output: "export",
  images: { unoptimized: true },
};

export default nextConfig;
