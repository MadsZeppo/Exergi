import { DashboardState } from "../dashboard-state";
import { getShopifyDashboard, money } from "../lib/shopify-dashboard";
import { MerchantPage, Status } from "../merchant-shell";

export default async function Page() {
  const result = await getShopifyDashboard();
  if (result.state !== "ready") return <MerchantPage eyebrow="Economics" title="Economic completeness" description="Observed amounts remain distinct from merchant assumptions and derived values."><DashboardState result={result} /></MerchantPage>;
  const company = result.data.company_state;
  if (!company) return <MerchantPage eyebrow="Economics" title="Economics are not ready" description="Revenue and cost identities appear after the initial import."><div className="notice">DATA NOT READY</div></MerchantPage>;
  return <MerchantPage eyebrow="Economics" title="Contribution-profit authority" description="Missing costs are never silently imputed."><div className="metric-grid"><article className="metric"><span>Net revenue</span><strong>{money(company.net_revenue, company.currency)}</strong></article><article className="metric"><span>Contribution profit</span><strong>{money(company.contribution_profit, company.currency)}</strong><small>{company.economic_authority}</small></article><article className="metric"><span>Refund rate</span><strong>{(company.refund_rate * 100).toFixed(1)}%</strong></article><article className="metric"><span>Discount rate</span><strong>{(company.discount_rate * 100).toFixed(1)}%</strong></article></div><section className="product-panel dashboard-section">{Object.entries(company.completeness).map(([key, value]) => <div className="health-row" key={key}><span>{key.replaceAll("_", " ")}</span><Status label={`${(value * 100).toFixed(0)}% covered`} tone={value === 1 ? "good" : "partial"} /></div>)}</section><div className="notice">Merchant assumptions are versioned and auditable. Values shown as contribution profit are withheld until every required component has explicit authority.</div></MerchantPage>;
}
