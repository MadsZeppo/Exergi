import { DashboardState } from "../dashboard-state";
import { getShopifyDashboard } from "../lib/shopify-dashboard";
import { MerchantPage } from "../merchant-shell";

export default async function Page() {
  const result = await getShopifyDashboard();
  if (result.state !== "ready") return <MerchantPage eyebrow="Customers" title="Observed customer state" description="Pseudonymous, point-in-time customer behavior without names, email, phone or addresses."><DashboardState result={result} /></MerchantPage>;
  const company = result.data.company_state;
  if (!company) return <MerchantPage eyebrow="Customers" title="Customer state is not ready" description="Customer features are generated only after canonical orders mature."><div className="notice">DATA NOT READY</div></MerchantPage>;
  const lifecycle = Object.entries(company.lifecycle_distribution);
  return <MerchantPage eyebrow="Customers" title="Lifecycle and repeat behavior" description="Lifecycle labels reflect observed cadence; they are not deterministic customer clones."><div className="metric-grid">{lifecycle.map(([label, count]) => <article className="metric" key={label}><span>{label}</span><strong>{count}</strong></article>)}</div><div className="notice">All identities are merchant-scoped HMAC pseudonyms. Exergi does not request customer names, email, phone or addresses.</div></MerchantPage>;
}
