import type { Metadata } from "next";
import { Inter } from "next/font/google";
import "./globals.css";

const inter = Inter({ subsets: ["latin"] });

export const metadata: Metadata = {
  title: "PaperChat — Chat with your documents",
  description: "Upload any PDF and have a conversation with it. Powered by RAG and Groq Llama 3.",
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en" suppressHydrationWarning>
      <body className={`${inter.className} antialiased bg-[#07070f] text-gray-100 min-h-screen`}>

        {/*
          MESH GRADIENT BACKGROUND
          ─────────────────────────
          Four blurred colour blobs positioned at different corners.
          Each is a plain div with a background colour and a large blur filter.
          Because they sit at `position: fixed` with `z-index: 0`, they stay
          pinned to the viewport and never scroll with content.
          The page content sits on top via `position: relative; z-index: 1`.

          Blob placement:
            1. Top-left    → violet       (primary accent colour)
            2. Bottom-right → indigo/blue  (cool contrast)
            3. Top-right   → purple       (bridges the two)
            4. Bottom-left → deep violet  (anchors the bottom)
        */}
        <div aria-hidden="true">
          {/* Blob 1 — deep purple, top-left */}
          <div
            className="mesh-blob"
            style={{
              width: "640px",
              height: "640px",
              background: "rgba(109, 40, 217, 0.45)",
              top: "-200px",
              left: "-180px",
            }}
          />
          {/* Blob 2 — hot pink, bottom-right */}
          <div
            className="mesh-blob"
            style={{
              width: "660px",
              height: "660px",
              background: "rgba(219, 39, 119, 0.38)",
              bottom: "-200px",
              right: "-180px",
            }}
          />
          {/* Blob 3 — fuchsia bridge, top-right (blends purple into pink) */}
          <div
            className="mesh-blob"
            style={{
              width: "420px",
              height: "420px",
              background: "rgba(192, 38, 211, 0.22)",
              top: "-60px",
              right: "8%",
            }}
          />
          {/* Blob 4 — rose anchor, bottom-left */}
          <div
            className="mesh-blob"
            style={{
              width: "360px",
              height: "360px",
              background: "rgba(159, 18, 57, 0.2)",
              bottom: "8%",
              left: "3%",
            }}
          />
        </div>

        {/* Page content — sits above the blobs */}
        <div className="relative z-10">
          {children}
        </div>

      </body>
    </html>
  );
}
