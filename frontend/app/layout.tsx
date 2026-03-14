import type { Metadata } from "next";
import { Geist, Geist_Mono } from "next/font/google";
import "./globals.css";
import Sidebar from "@/components/layout/Sidebar";

const geistSans = Geist({ subsets: ["latin"], variable: "--font-geist-sans" });
const geistMono = Geist_Mono({ subsets: ["latin"], variable: "--font-geist-mono" });

export const metadata: Metadata = {
  title: "Arlo",
  description: "AI-powered research and web intelligence",
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en">
      <body className={`${geistSans.variable} ${geistMono.variable}`}>
        <div style={{ width: "100%", height: "100vh", display: "flex", overflow: "hidden" }}>
          <Sidebar />
          <main style={{ flex: 1, minWidth: 0, background: "var(--page-bg)", overflowY: "auto", position: "relative" }}>
            {children}
          </main>
        </div>
      </body>
    </html>
  );
}
