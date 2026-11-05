import type { Metadata, Viewport } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "NGULIK BASS STUDIO",
  description: "Feel the groove. Read the notes.",
};
export const viewport: Viewport = { width: "device-width", initialScale: 1, themeColor: "#0b0c0d" };

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="id">
      <body className="min-h-screen font-sans antialiased">{children}</body>
    </html>
  );
}
