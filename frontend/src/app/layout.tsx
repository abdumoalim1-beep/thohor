import type { Metadata } from "next";
import { Geist_Mono, IBM_Plex_Sans_Arabic, JetBrains_Mono } from "next/font/google";
import "./globals.css";

// IBM Plex Sans Arabic — Geist has no Arabic glyphs at all, so Arabic text
// was silently falling back to the OS default font. This family covers
// Arabic + Latin with matching metrics (numbers line up cleanly with
// Arabic text), at the weight range a premium SaaS product needs.
const ibmPlexArabic = IBM_Plex_Sans_Arabic({
  variable: "--font-ibm-plex-arabic",
  subsets: ["arabic", "latin"],
  weight: ["300", "400", "500", "600", "700"],
});

const geistMono = Geist_Mono({
  variable: "--font-geist-mono",
  subsets: ["latin"],
});

// Used by the public landing/onboarding pages (frontend/src/app/landing.css),
// which follow a separate design spec from the workspace app.
const jetbrainsMono = JetBrains_Mono({
  variable: "--font-jetbrains-mono",
  subsets: ["latin"],
  weight: ["400", "500"],
});

export const metadata: Metadata = {
  title: "ظهور — يراقب ظهور متجرك ويخبرك ماذا تحسّن",
  description: "ظهور يراقب ظهور متجرك في Google ومحركات AI، يفهم أين تخسر أمام المنافسين، ويخبرك ماذا تحسّن.",
};

export default function RootLayout({ children }: LayoutProps<"/">) {
  return (
    <html
      lang="ar"
      dir="rtl"
      className={`${ibmPlexArabic.variable} ${geistMono.variable} ${jetbrainsMono.variable} h-full antialiased`}
    >
      <body className="min-h-full flex flex-col bg-bg text-text">{children}</body>
    </html>
  );
}
