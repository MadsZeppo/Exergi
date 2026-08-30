import { DashboardState } from "../dashboard-state";
import { MerchantPage, Status } from "../merchant-shell";
import { getShopifyDashboard, money } from "../lib/shopify-dashboard";

export default async function Page() {
  const result = await getShopifyDashboard();
  if (result.state !== "ready") return <MerchantPage eyebrow="Overview" title="Your commercial system" description="Observed Shopify history, explicit economic authority and decisions that preserve the evidence boundary."><DashboardState result={result} /></MerchantPage>;
  const { company_state: company, connection, sync, decision_cards: decisions } = result.data;
  if (!company) return <MerchantPage eyebrow="Overview" title="Data is syncing" description="No metric is shown until mature canonical orders are available."><section className="product-panel"><div className="health-row"><span>Connection</span><Status label={String(connection.status ?? "UNKNOWN")} tone="good" /></div><div className="health-row"><span>Initial sync</span><Status label={String(sync.status ?? "NOT STARTED")} tone="partial" /></div></section><div className="notice">DATA NOT READY — no production values have been fabricated.</div></MerchantPage>;
  return <MerchantPage eyebrow="Overview" title="What changed, and what deserves attention" description={`Point-in-time state as of ${new Date(company.as_of).toLocaleDateString()}.`}>
    <div className="metric-grid">
      <article className="metric"><span>Net revenue</span><strong>{money(company.net_revenue, company.currency)}</strong></article>
      <article className="metric"><span>Contribution profit</span><strong>{money(company.contribution_profit, company.currency)}</strong><small>{company.economic_authority}</small></article>
      <article className="metric"><span>Repeat net revenue</span><strong>{money(company.repeat_revenue, company.currency)}</strong></article>
      <article className="metric"><span>Observed customers</span><strong>{company.customer_count.toLocaleString()}</strong></article>
    </div>
    <section className="product-panel dashboard-section"><div className="section-head"><div><p className="section-kicker">Connection</p><h2>Shopify data boundary</h2></div><Status label={String(connection.status)} tone="good" /></div><div className="health-row"><span>Sync</span><Status label={String(sync.status ?? "NOT STARTED")} tone={sync.status === "COMPLETED" ? "good" : "partial"} /></div><div className="health-row"><span>Economic authority</span><Status label={company.economic_authority} tone={company.contribution_profit === null ? "partial" : "good"} /></div></section>
    {decisions[0] ? <article className="opportunity-card dashboard-section"><Status label={decisions[0].recommendation.replaceAll("_", " ")} tone={decisions[0].recommendation === "AVOID" ? "neutral" : "partial"} /><h2>{decisions[0].observation}</h2><p>{decisions[0].uncertainty}</p><a className="primary-link compact" href="/decisions">Why this decision? →</a></article> : null}
  </MerchantPage>;
}
