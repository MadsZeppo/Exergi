import assert from "node:assert/strict";
import test from "node:test";

// @ts-expect-error Node's strip-types test runner intentionally imports TypeScript source.
import { canQueueSync, GENERIC_SYNC_FAILURE, safeSyncFailureSummary, syncActionLabel } from "../app/data-integrations/sync-status.ts";

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

test("permits a fresh read-only sync after a completed import", () => {
  assert.equal(canQueueSync("COMPLETED"), true);
  assert.equal(syncActionLabel("COMPLETED", false), "Sync now");
});

test("keeps active and unknown sync states non-queueable", () => {
  for (const status of ["QUEUED", "RUNNING", "SYNCING", "UNKNOWN"]) {
    assert.equal(canQueueSync(status), false);
  }
  assert.equal(canQueueSync("FAILED"), true);
  assert.equal(canQueueSync("NOT_STARTED"), true);
  assert.equal(syncActionLabel("FAILED", false), "Retry sync");
  assert.equal(syncActionLabel("NOT_STARTED", false), "Start sync");
  assert.equal(syncActionLabel("COMPLETED", true), "Queueing…");
});
