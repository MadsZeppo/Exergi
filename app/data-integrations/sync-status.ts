export const GENERIC_SYNC_FAILURE =
  "Read-only Shopify sync failed; inspect server-side diagnostics.";

const QUEUEABLE_SYNC_STATUSES = new Set(["NOT_STARTED", "FAILED", "COMPLETED"]);

const SAFE_SHOPIFY_FAILURE =
  /^Shopify (customers|products|orders) bulk operation (FAILED|CANCELED|EXPIRED|REJECTED): [A-Z0-9_]+$/;

export function safeSyncFailureSummary(value: unknown): string {
  if (typeof value !== "string") return GENERIC_SYNC_FAILURE;
  const summary = value.trim();
  if (summary === GENERIC_SYNC_FAILURE || SAFE_SHOPIFY_FAILURE.test(summary)) return summary;
  return GENERIC_SYNC_FAILURE;
}

export function canQueueSync(status: string): boolean {
  return QUEUEABLE_SYNC_STATUSES.has(status);
}

export function syncActionLabel(status: string, submitting: boolean): string {
  if (submitting) return "Queueing…";
  if (status === "COMPLETED") return "Sync now";
  if (status === "NOT_STARTED") return "Start sync";
  return "Retry sync";
}
