import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import test from "node:test";

// @ts-expect-error Node's strip-types test runner intentionally imports TypeScript source.
import { GET } from "../app/api/cron/retention/route.ts";
// @ts-expect-error Node's strip-types test runner intentionally imports TypeScript source.
import { bypassesClerk } from "../app/lib/cron-auth.ts";

const SECRET = "s".repeat(40);

function request(authorization?: string): Request {
  return new Request("https://exergi.vercel.app/api/cron/retention", {
    headers: authorization ? { Authorization: authorization } : {},
  });
}

test("only the exact retention cron path bypasses Clerk", () => {
  assert.equal(bypassesClerk("/api/cron/retention"), true);
  for (const path of [
    "/api/cron/retention/",
    "/api/cron/retention/extra",
    "/api/shop-context",
    "/api/v1/shopify/connect",
    "/onboarding",
  ]) assert.equal(bypassesClerk(path), false, `${path} must still enter Clerk middleware`);
  const proxySource = readFileSync(new URL("../proxy.ts", import.meta.url), "utf8");
  assert.match(proxySource, /if \(bypassesClerk\(request\.nextUrl\.pathname\)\)/);
  assert.match(proxySource, /return clerkProxy\(request, event\)/);
});

test("missing server secret fails closed", async () => {
  delete process.env.CRON_SECRET;
  process.env.NEXT_PUBLIC_EXERGI_API_URL = "https://api.example";
  const response = await GET(request(`Bearer ${SECRET}`));
  assert.equal(response.status, 401);
  assert.equal((await response.json()).detail, "invalid maintenance authentication");
});

test("missing or incorrect incoming bearer secret is rejected", async () => {
  process.env.CRON_SECRET = SECRET;
  process.env.NEXT_PUBLIC_EXERGI_API_URL = "https://api.example";
  for (const authorization of [undefined, "Bearer wrong", SECRET]) {
    const response = await GET(request(authorization));
    assert.equal(response.status, 401);
    assert.equal((await response.json()).detail, "invalid maintenance authentication");
  }
});

test("valid bearer is forwarded server-side under the maintenance header", async () => {
  process.env.CRON_SECRET = SECRET;
  process.env.NEXT_PUBLIC_EXERGI_API_URL = "https://api.example/";
  const originalFetch = globalThis.fetch;
  globalThis.fetch = (async (input: string | URL | Request, init?: RequestInit) => {
    assert.equal(String(input), "https://api.example/api/v1/maintenance/daily");
    assert.equal(init?.method, "POST");
    const headers = new Headers(init?.headers);
    assert.equal(headers.get("X-Exergi-Maintenance-Secret"), SECRET);
    assert.equal(headers.get("Authorization"), null);
    return Response.json({ status: "COMPLETED", rows_deleted: {} });
  }) as typeof fetch;
  try {
    const response = await GET(request(`Bearer ${SECRET}`));
    const body = await response.text();
    assert.equal(response.status, 200);
    assert.equal(body.includes(SECRET), false);
    assert.deepEqual(JSON.parse(body), { status: "COMPLETED", rows_deleted: {} });
  } finally {
    globalThis.fetch = originalFetch;
  }
});
