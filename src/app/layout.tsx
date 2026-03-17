import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "SENTINEL — Satellite Collision Detection",
  description: "Decentralised satellite collision detection using autonomous agents",
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html lang="en">
      <body>{children}</body>
    </html>
  );
}
