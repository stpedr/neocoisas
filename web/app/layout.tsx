import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "Auto Niche Engine",
  description:
    "Gere ideias de vídeo, aprove estilo Tinder e planeje o projeto no Kanban.",
};

export default function RootLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <html lang="pt-BR">
      <body>{children}</body>
    </html>
  );
}
