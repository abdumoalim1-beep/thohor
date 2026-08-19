import type { Metadata } from "next";
import { Geist_Mono, JetBrains_Mono } from "next/font/google";
import localFont from "next/font/local";
import "./globals.css";

// Thmanyah Sans — the site's brand typeface (self-hosted, licensed font
// family), covers Arabic + Latin. Replaces the earlier IBM Plex Sans
// Arabic placeholder everywhere the --font-ibm-plex-arabic variable was
// used (kept the same variable name to avoid touching every consumer).
const thmanyahSans = localFont({
  variable: "--font-ibm-plex-arabic",
  src: [
    { path: "../fonts/thmanyah-sans/thmanyahsans-Light.woff2", weight: "300", style: "normal" },
    { path: "../fonts/thmanyah-sans/thmanyahsans-Regular.woff2", weight: "400", style: "normal" },
    { path: "../fonts/thmanyah-sans/thmanyahsans-Medium.woff2", weight: "500", style: "normal" },
    { path: "../fonts/thmanyah-sans/thmanyahsans-Bold.woff2", weight: "700", style: "normal" },
    { path: "../fonts/thmanyah-sans/thmanyahsans-Black.woff2", weight: "900", style: "normal" },
  ],
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
  title: "ظهور — يراقب ظهور علامتك ويخبرك ماذا تحسّن",
  description: "ظهور يراقب ظهور علامتك التجارية في Google ومحركات الذكاء الاصطناعي، يفهم أين تخسر أمام المنافسين، ويخبرك ماذا تحسّن",
};

export default function RootLayout({ children }: LayoutProps<"/">) {
  return (
    <html
      lang="ar"
      dir="rtl"
      className={`${thmanyahSans.variable} ${geistMono.variable} ${jetbrainsMono.variable} h-full antialiased`}
    >
      <body className="min-h-full flex flex-col bg-bg text-text">{children}</body>
    </html>
  );
}
