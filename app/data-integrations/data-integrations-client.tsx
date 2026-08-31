"use client";

import { useAuth } from "@clerk/nextjs";
import { useRouter } from "next/navigation";
import { useEffect, useMemo, useState } from "react";

import { MerchantPage, Status } from "../merchant-shell";
import { safeSyncFailureSummary } from "./sync-status";

type Props = {
  apiBase: string;
  shop: string;
  connection: Record<string, unknown>;
  sync: Record<string, unknown>;
  quality: Record<string, unknown>;
};

const RETRYABLE = new Set(["FAILED", "NOT_STARTED"]);
const POLLING = new Set(["QUEUED", "RUNNING", "SYNCING"]);

function text(value: unknown, fallback: string): string {
  return typeof value === "string" && value ? value : fallback;
}

export function DataIntegrationsClient({ apiBase, shop, connection, sync, quality }: Props) {
  const { getToken, isLoaded, isSignedIn } = useAuth();
  const router = useRouter();
  const [syncStatus, setSyncStatus] = useState(text(sync.status, "NOT_STARTED"));
  const [syncFailure, setSyncFailure] = useState(
    text(sync.status, "NOT_STARTED") === "FAILED"
      ? safeSyncFailureSummary(sync.error_summary)
      : "",
  );
  const [error, setError] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const base = apiBase.replace(/\/$/, "");
  const connectionStatus = text(connection.status, "UNKNOWN");
  const scopes = Array.isArray(connection.scopes) ? connection.scopes : [];
  const history = useMemo(() => {
    if (connection.history === "ALL_APPROVED_ORDERS") return "ALL_APPROVED_ORDERS";
    if (connection.history === "SHOPIFY_DEFAULT_ORDER_WINDOW") {
      return "SHOPIFY_DEFAULT_ORDER_WINDOW";
    }
    return scopes.includes("read_all_orders")
      ? "ALL_APPROVED_ORDERS"
      : "SHOPIFY_DEFAULT_ORDER_WINDOW";
  }, [connection.history, scopes]);
  const canRetry = connectionStatus === "CONNECTED"
    && RETRYABLE.has(syncStatus)
    && isLoaded
    && isSignedIn
    && !submitting
    && Boolean(base && shop);

  useEffect(() => {
    if (!POLLING.has(syncStatus) || !isSignedIn || !base || !shop) return;
    let cancelled = false;
    const poll = async () => {
      try {
        const token = await getToken();
        if (!token) throw new Error("Authentication token is unavailable.");
        const response = await fetch(
          `${base}/api/v1/shopify/dashboard?shop=${encodeURIComponent(shop)}`,
          { headers: { Authorization: `Bearer ${token}` }, cache: "no-store" },
        );
        if (!response.ok) throw new Error(`Sync status returned ${response.status}.`);
        const snapshot = await response.json() as {
          sync?: { status?: unknown; error_summary?: unknown };
        };
        const observed = text(snapshot.sync?.status, "NOT_STARTED");
        if (!cancelled) {
          setSyncStatus(observed);
          setSyncFailure(
            observed === "FAILED"
              ? safeSyncFailureSummary(snapshot.sync?.error_summary)
              : "",
          );
          if (!POLLING.has(observed)) router.refresh();
        }
      } catch (reason) {
        if (!cancelled) {
          setError(reason instanceof Error ? reason.message : "Sync status is unavailable.");
        }
      }
    };
    void poll();
    const interval = window.setInterval(() => { void poll(); }, 2500);
    return () => {
      cancelled = true;
      window.clearInterval(interval);
    };
  }, [base, getToken, isSignedIn, router, shop, syncStatus]);

  async function retrySync() {
    if (!canRetry) return;
    setError("");
    setSubmitting(true);
    try {
      const token = await getToken();
      if (!token) throw new Error("Authentication token is unavailable.");
      const response = await fetch(
        `${base}/api/v1/shopify/sync?shop=${encodeURIComponent(shop)}`,
        { method: "POST", headers: { Authorization: `Bearer ${token}` } },
      );
      const body = await response.json() as { status?: string; detail?: string };
      if (!response.ok || body.status !== "QUEUED") {
        throw new Error(body.detail ?? "The read-only sync could not be queued.");
      }
      setSyncStatus("QUEUED");
      setSyncFailure("");
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "The sync retry failed.");
    } finally {
      setSubmitting(false);
    }
  }

  const displayedSync = syncStatus === "RUNNING" ? "SYNCING" : syncStatus;
  return <MerchantPage eyebrow="Data & integrations" title="Shopify connection" description="Exergi requests no write scopes.">
    <section className="product-panel">
      <div className="health-row"><span>Connection</span><Status label={connectionStatus} tone={connectionStatus === "CONNECTED" ? "good" : "partial"} /></div>
      <div className="health-row"><span>GraphQL Admin API</span><Status label={text(connection.api_version, "UNKNOWN")} tone="good" /></div>
      <div className="health-row"><span>History access</span><Status label={history} tone="partial" /></div>
      <div className="health-row"><span>Latest sync</span><Status label={displayedSync} tone={syncStatus === "COMPLETED" ? "good" : "partial"} /></div>
      <div className="health-row"><span>Data readiness</span><Status label={text(quality.status, "DATA_NOT_READY")} tone="partial" /></div>
    </section>
    <section className="product-panel dashboard-section">
      <h2>Read-only synchronization</h2>
      <p>Retry resumes the existing Shopify connection. It does not restart OAuth or request new scopes.</p>
      <button className="sync-retry-button" type="button" onClick={retrySync} disabled={!canRetry}>
        {submitting ? "Queueing…" : POLLING.has(syncStatus) ? displayedSync : "Retry sync"}
      </button>
      {syncStatus === "FAILED" && syncFailure ? <p className="form-note" role="alert"><strong>Latest failure:</strong> {syncFailure}</p> : null}
      {error ? <p className="form-note">{error}</p> : null}
    </section>
  </MerchantPage>;
}
