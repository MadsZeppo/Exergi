import { MerchantPage, Status } from "../../merchant-shell";

export default function Page() {
  return <MerchantPage eyebrow="Settings / security" title="Read-only by construction" description="Credential, identity, retention and evidence boundaries for this workspace."><section className="product-panel"><div className="health-row"><span>Shopify write scopes</span><Status label="NONE" tone="good" /></div><div className="health-row"><span>Offline tokens</span><Status label="ENCRYPTED SERVER-SIDE" tone="good" /></div><div className="health-row"><span>Customer direct identifiers</span><Status label="NOT REQUESTED" tone="good" /></div><div className="health-row"><span>Autonomous actions</span><Status label="DISABLED" tone="neutral" /></div><div className="health-row"><span>Causal claims from history</span><Status label="DISABLED" tone="neutral" /></div></section><a className="primary-link" href="/data-integrations">Manage Shopify connection →</a></MerchantPage>;
}
