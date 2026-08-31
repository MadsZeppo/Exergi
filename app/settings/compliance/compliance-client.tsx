"use client";

import { useAuth } from "@clerk/nextjs";
import { useEffect, useState } from "react";

import { MerchantPage, Status } from "../../merchant-shell";

type Dashboard = {
  agreement: { required_version: string; accepted: boolean; accepted_at: string | null };
  latest_retention_run: null | { started_at: string; completed_at: string | null; status: string; rows_deleted_json: Record<string, number>; jobs_processed: number };
  privacy_jobs: { pending: number; failed: number };
  privacy_exports_ready: number;
  webhooks: { topic: string; declared: boolean; deployment_status: string; verified_at: string | null }[];
};

export function ComplianceClient({ apiBase }: { apiBase: string }) {
  const { getToken, isSignedIn } = useAuth();
  const [data, setData] = useState<Dashboard | null>(null);
  const [error, setError] = useState("");
  useEffect(() => {
    if (!isSignedIn || !apiBase) return;
    let cancelled = false;
    void getToken().then(async (token) => {
      if (!token) throw new Error("Authentication token unavailable.");
      const response = await fetch(`${apiBase.replace(/\/$/, "")}/api/v1/shopify/compliance`, { headers: { Authorization: `Bearer ${token}` }, cache: "no-store" });
      if (!response.ok) throw new Error("Compliance status could not be loaded.");
      if (!cancelled) setData(await response.json() as Dashboard);
    }).catch((reason: unknown) => { if (!cancelled) setError(reason instanceof Error ? reason.message : "Compliance status unavailable."); });
    return () => { cancelled = true; };
  }, [apiBase, getToken, isSignedIn]);
  return <MerchantPage eyebrow="Compliance" title="Retention and privacy operations" description="Data-minimized operational evidence. No raw customer data is shown here.">
    {error ? <div className="notice warning">{error}</div> : null}
    <section className="metric-grid">
      <div className="metric"><span>Agreement version</span><strong>{data?.agreement.required_version ?? "—"}</strong><Status label={data?.agreement.accepted ? "ACCEPTED" : "REQUIRED"} tone={data?.agreement.accepted ? "good" : "partial"} /></div>
      <div className="metric"><span>Latest retention run</span><strong>{data?.latest_retention_run?.status ?? "NOT RUN"}</strong><small>{data?.latest_retention_run?.completed_at ?? "No completed run recorded"}</small></div>
      <div className="metric"><span>Pending / failed privacy jobs</span><strong>{data ? `${data.privacy_jobs.pending} / ${data.privacy_jobs.failed}` : "—"}</strong><small>{data?.privacy_exports_ready ?? 0} export(s) ready</small></div>
    </section>
    <section className="product-panel dashboard-section"><h2>Rows deleted by category</h2>
      <table className="compliance-table"><tbody>{Object.entries(data?.latest_retention_run?.rows_deleted_json ?? {}).map(([category, count]) => <tr key={category}><th>{category}</th><td>{count}</td></tr>)}</tbody></table>
      {!data?.latest_retention_run ? <p>No successful daily retention execution has been recorded yet.</p> : null}
    </section>
    <section className="product-panel dashboard-section"><h2>Required Shopify webhooks</h2>
      <table className="compliance-table"><thead><tr><th>Topic</th><th>Declaration</th><th>Live verification</th></tr></thead><tbody>{(data?.webhooks ?? []).map((webhook) => <tr key={webhook.topic}><td><code>{webhook.topic}</code></td><td>{webhook.declared ? "DECLARED" : "MISSING"}</td><td>{webhook.deployment_status}</td></tr>)}</tbody></table>
      <p>“Declared” is configuration evidence only. It becomes “LIVE VERIFIED” only after the Shopify app version is deployed and its timestamp is recorded in the backend environment.</p>
    </section>
  </MerchantPage>;
}
