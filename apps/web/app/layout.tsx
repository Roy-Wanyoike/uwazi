import type { Metadata } from "next";
import Link from "next/link";
import { SpeedInsights } from "@vercel/speed-insights/next";
import "./globals.css";

export const metadata: Metadata = {
  title: "Uwazi — Open Contracting Intelligence for African Procurement",
  description:
    "An agentic AI on MCP that evaluates public tenders in 30 minutes — with a hard rule that the AI proposes and the procurement officer decides.",
  openGraph: {
    title: "Uwazi — Open Contracting Intelligence for African Procurement",
    description:
      "An agentic AI on MCP that evaluates public tenders in 30 minutes — with a hard rule that the AI proposes and the procurement officer decides.",
    type: "website",
  },
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en">
      <body>
        <header className="header">
          <div className="container header-inner">
            <Link href="/" className="brand">
              <span className="brand-dot" />
              Uwazi
            </Link>
            <nav className="nav">
              <Link href="/tenders">Tenders</Link>
              <Link href="/notices">Open Notices</Link>
              <a href="https://github.com/Roy-Wanyoike/uwazi" target="_blank" rel="noreferrer">
                GitHub ↗
              </a>
            </nav>
          </div>
        </header>
        <main>{children}</main>
        <footer className="footer">
          <div className="container">
            <div style={{ display: "flex", justifyContent: "space-between", flexWrap: "wrap", gap: 16 }}>
              <div>
                <strong>Uwazi</strong> · MIT-licensed · Built for the Agentic AI for Africa Innovation Challenge
              </div>
              <div>
                <span className="badge badge-ai">AI recommends · The officer decides</span>
              </div>
            </div>
          </div>
        </footer>
        <SpeedInsights />
      </body>
    </html>
  );
}
