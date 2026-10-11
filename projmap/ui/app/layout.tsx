import type { Metadata, Viewport } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "ProjMap — mestre",
  description: "Editor de projeção mapeada: superfícies sobre a foto, saída ao vivo no projetor.",
  // PWA: "Adicionar à tela inicial" no celular abre direto o remote (F6).
  manifest: "/manifest.webmanifest",
  appleWebApp: { capable: true, title: "ProjMap", statusBarStyle: "black-translucent" },
};

export const viewport: Viewport = {
  width: "device-width",
  initialScale: 1,
  // Sem zoom por pinça: no celular o gesto é para arrastar cantos.
  maximumScale: 1,
  themeColor: "#0b0f17",
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="pt-BR">
      <body>{children}</body>
    </html>
  );
}
