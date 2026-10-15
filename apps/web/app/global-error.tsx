"use client";

import { useEffect } from "react";

/**
 * Next.js App-Router global error boundary.
 *
 * Catches any error that escapes a Server Component (e.g., an uncaught
 * TypeError from accessing a property on an undefined value, or a
 * thrown error during server-action routing). Without this, Next.js
 * shows a generic "This page couldn't load. A server error occurred."
 * overlay that gives the user zero diagnostic information.
 *
 * With this in place, the user gets a friendly error card that explains
 * what to check (Vercel URL, FastAPI service status, UWAZI_API_URL
 * binding) and what to curl to diagnose.
 */
export default function GlobalError({
  error,
  reset,
}: {
  error: Error & { digest?: string };
  reset: () => void;
}) {
  useEffect(() => {
    console.error("[Uwazi global error]", error);
  }, [error]);

  return (
    <html lang="en">
      <body style={{ margin: 0, fontFamily: "system-ui, sans-serif", background: "#f8fafc" }}>
        <div
          style={{
            maxWidth: 640,
            margin: "80px auto",
            padding: "24px",
            background: "white",
            borderRadius: 12,
            border: "1px solid #e2e8f0",
          }}
        >
          <h1 style={{ margin: "0 0 8px", fontSize: 22, color: "#dc2626" }}>
            Something went wrong on the server
          </h1>
          <p style={{ color: "#475569", margin: "0 0 16px" }}>
            Uwazi hit an unexpected error while rendering this page. The most common causes:
          </p>
          <ul style={{ color: "#475569", lineHeight: 1.7 }}>
            <li>
              The FastAPI service is still cold-starting (Neon DB wakeup
              takes 3-5 seconds on the first request after idle).
            </li>
            <li>
              The <code>UWAZI_API_URL</code> Vercel services binding isn&apos;t
              injected yet (rare — usually resolves on a second request).
            </li>
            <li>
              The Neon Postgres connection timed out (Hobby plan has a 10s
              function timeout; check the Vercel function logs).
            </li>
          </ul>
          <p style={{ color: "#475569", margin: "16px 0 8px" }}>
            To diagnose, curl these from your laptop against the deployed URL:
          </p>
          <pre
            style={{
              background: "#f8fafc",
              border: "1px solid #e2e8f0",
              borderRadius: 6,
              padding: 12,
              overflowX: "auto",
              fontSize: 12,
            }}
          >
{`# 1. Verify the FastAPI service is healthy
curl https://<your-vercel-url>/api/v1/healthz

# 2. Check whether the sample data is seeded into Neon
curl https://<your-vercel-url>/api/v1/admin/seed-status

# 3. Force a re-seed if the DB looks empty
curl -X POST https://<your-vercel-url>/api/v1/admin/reseed`}
          </pre>
          <p style={{ color: "#94a3b8", fontSize: 12, margin: "12px 0 0" }}>
            Error message: <code>{error.message || "(no message)"}</code>
            {error.digest && (
              <>
                {"  ·  "}
                Digest: <code>{error.digest}</code>
              </>
            )}
          </p>
          <button
            onClick={reset}
            style={{
              marginTop: 16,
              padding: "8px 16px",
              background: "#2563eb",
              color: "white",
              border: "none",
              borderRadius: 6,
              cursor: "pointer",
              font: "inherit",
            }}
          >
            Try again →
          </button>
        </div>
      </body>
    </html>
  );
}
