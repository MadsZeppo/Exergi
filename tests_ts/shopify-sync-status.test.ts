import assert from "node:assert/strict";
import test from "node:test";

// @ts-expect-error Node's strip-types test runner intentionally imports TypeScript source.
import { GENERIC_SYNC_FAILURE, safeSyncFailureSummary } from "../app/data-integrations/sync-status.ts";

test("renders only backend-safe Shopify sync failure summaries", () => {
  assert.equal(
    safeSyncFailureSummary("Shopify orders bulk operation REJECTED: INVALID_QUERY"),
    "Shopify orders bulk operation REJECTED: INVALID_QUERY",
  );
  assert.equal(
    safeSyncFailureSummary("Shopify customers bulk operation FAILED: ACCESS_DENIED"),
    "Shopify customers bulk operation FAILED: ACCESS_DENIED",
  );
});

test("fails closed for missing or potentially sensitive failure text", () => {
  for (const value of [
    undefined,
    "",
    "request failed with token shpat_secret",
    "Shopify customers bulk operation FAILED: contains-lowercase",
  ]) {
    assert.equal(safeSyncFailureSummary(value), GENERIC_SYNC_FAILURE);
  }
});
