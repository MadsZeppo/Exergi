import { DashboardState } from "../dashboard-state";
import { getShopifyDashboard } from "../lib/shopify-dashboard";
import { MerchantPage, Status } from "../merchant-shell";

export default async function Page() {
  const result = await getShopifyDashboard();
  if (result.state !== "ready") return <MerchantPage eyebrow="Data & integrations" title="Shopify connection" description="Read-only access, explicit permissions and observable sync state."><DashboardState result={result} /></MerchantPage>;
  const { connection, sync, data_quality: quality } = result.data;
  return <MerchantPage eyebrow="Data & integrations" title="Shopify connection" description="Exergi requests no write scopes."><section className="product-panel"><div className="health-row"><span>Connection</span><Status label={String(connection.status)} tone="good" /></div><div className="health-row"><span>GraphQL Admin API</span><Status label={String(connection.api_version)} tone="good" /></div><div className="health-row"><span>History access</span><Status label={String(connection.history)} tone="partial" /></div><div className="health-row"><span>Latest sync</span><Status label={String(sync.status ?? "NOT STARTED")} tone={sync.status === "COMPLETED" ? "good" : "partial"} /></div><div className="health-row"><span>Data readiness</span><Status label={String(quality.status ?? "DATA NOT READY")} tone="partial" /></div></section></MerchantPage>;
}
