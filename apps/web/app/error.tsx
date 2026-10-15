"use client";

/**
 * Route-level error boundary for the /tenders/[id] route (and any sibling
 * routes that share this error.tsx).
 *
 * Catches errors thrown DURING client-side rendering (after the page has
 * hydrated). For Server-Component-time errors, see app/global-error.tsx.
 */
import Link from "next/link";
import { useEffect } from "react";

export default function Error({
  error,
  reset,
}: {
  error: Error & { digest?: string };
  reset: () => void;
}) {
  useEffect(() => {
    console.error("[Uwazi route error]", error);
  }, [error]);

  return (
    <div className="container" style={{ paddingTop: 32, maxWidth: 720 }}>
      <div className="card" style={{ borderColor: "var(--crit)" }}>
        <h3 style={{ color: "var(--crit)", marginTop: 0 }}>
          This page hit a runtime error
        </h3>
        <p className="bid-meta">
          The most common cause is a malformed API response — the FastAPI
          service may be cold-starting, or the Neon DB connection may have
          timed out on the first request after idle.
        </p>
        <p className="bid-meta" style={{ marginTop: 12 }}>
          Try the actions below, in order:
        </p>
        <ol style={{ color: "var(--fg-subtle)", paddingLeft: 20 }}>
          <li>Wait 5 seconds (Neon cold-start), then click <strong>Try again</strong>.</li>
          <li>
            Open <Link href="/tenders" style={{ color: "var(--accent)" }}>the tenders list</Link>{" "}
            to confirm the API is responding.
          </li>
          <li>
            Hit <code>POST /api/v1/admin/reseed</code> from your laptop to
            force a fresh seed into Neon.
          </li>
        </ol>
        <p className="bid-meta" style={{ marginTop: 12 }}>
          Error: <code>{error.message || "(no message)"}</code>
          {error.digest && <> · Digest: <code>{error.digest}</code></>}
        </p>
        <button
          onClick={reset}
          className="btn btn-primary"
          style={{ marginTop: 8 }}
        >
          Try again →
        </button>
      </div>
    </div>
  );
}
