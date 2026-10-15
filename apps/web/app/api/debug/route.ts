/**
 * Debug endpoint — runs in the Next.js server context (same as Server
 * Components). Use this to verify which env vars Vercel actually
 * injected into the `web` service.
 *
 * Hit it with: curl https://<your-vercel-url>/api/debug
 *
 * Don't deploy this to production — it leaks env var names + values.
 * (Variable NAMES are always shown; VALUES are only shown for safe ones.)
 */

import { NextResponse } from "next/server";

export const dynamic = "force-dynamic";

export async function GET() {
  // Gather all env var NAMES (always safe to show)
  const allKeys = Object.keys(process.env).sort();

  // For these specific vars, show the value too (so we can debug the
  // Vercel services binding). Mask any secrets.
  const safeToShow = [
    "UWAZI_API_URL",
    "DATABASE_URL",
    "OPENAI_BASE_URL",
    "OPENAI_MODEL",
    "VERCEL",
    "VERCEL_URL",
    "VERCEL_PROJECT_ID",
    "VERCEL_ENV",
    "AUTO_SEED_ON_START",
    "UWAZI_DB_PATH",
    "NEXT_PUBLIC_VERCEL_URL",
    "DEPLOYMENT_URL",
  ];

  const safeValues: Record<string, string> = {};
  for (const key of safeToShow) {
    const v = process.env[key];
    if (v === undefined) {
      safeValues[key] = "(undefined)";
    } else if (v === "") {
      safeValues[key] = "(empty string)";
    } else if (key.includes("KEY") || key.includes("PASSWORD") || key.includes("SECRET")) {
      safeValues[key] = `*** (${v.length} chars)`;
    } else if (key === "DATABASE_URL") {
      // Show the URL but mask the password
      const masked = v.replace(/(\/\/[^:]+:)[^@]+@/, "$1***@");
      safeValues[key] = masked;
    } else {
      safeValues[key] = v;
    }
  }

  // Try a fetch to the bound API URL to see if it's reachable
  const bound = process.env.UWAZI_API_URL;
  let fetchTest: Record<string, unknown> = { attempted: false };
  if (bound) {
    fetchTest.attempted = true;
    fetchTest.url = `${bound.replace(/\/$/, "")}/api/v1/healthz`;
    try {
      const start = Date.now();
      const res = await fetch(`${bound.replace(/\/$/, "")}/api/v1/healthz`, {
        signal: AbortSignal.timeout(5000),
      });
      fetchTest.status = res.status;
      fetchTest.elapsed_ms = Date.now() - start;
      fetchTest.body = (await res.text()).slice(0, 200);
    } catch (e) {
      fetchTest.error = e instanceof Error ? e.message : String(e);
    }
  }

  // Also try a relative fetch (the vercel.json rewrite path)
  let relativeFetch: Record<string, unknown> = { attempted: true, url: "/api/v1/healthz" };
  try {
    const start = Date.now();
    // On Vercel server-side, relative fetches don't work — need absolute.
    // Use VERCEL_URL to construct the absolute URL.
    const host = process.env.VERCEL_URL
      ? `https://${process.env.VERCEL_URL}`
      : process.env.NEXT_PUBLIC_VERCEL_URL
      ? `https://${process.env.NEXT_PUBLIC_VERCEL_URL}`
      : "http://localhost:3000";
    relativeFetch.host = host;
    const res = await fetch(`${host}/api/v1/healthz`, {
      signal: AbortSignal.timeout(5000),
    });
    relativeFetch.status = res.status;
    relativeFetch.elapsed_ms = Date.now() - start;
    relativeFetch.body = (await res.text()).slice(0, 200);
  } catch (e) {
    relativeFetch.error = e instanceof Error ? e.message : String(e);
  }

  return NextResponse.json({
    now: new Date().toISOString(),
    runtime: "Next.js Route Handler (server-side)",
    env_var_count: allKeys.length,
    env_var_names: allKeys,
    safe_values: safeValues,
    fetch_tests: {
      bound_url: fetchTest,
      relative_url: relativeFetch,
    },
    note: "If UWAZI_API_URL is '(undefined)' or '(empty string)', the Vercel services binding is not injecting the env var into the Next.js server context. Fix: recheck vercel.json — the binding must be on the `web` service, env var name must match exactly. See https://vercel.com/docs/services.",
  });
}
