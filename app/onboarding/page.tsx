import { cookies } from "next/headers";

import { MerchantPage, Status } from "../merchant-shell";

export default async function Page({ searchParams }: { searchParams: Promise<Record<string, string | string[] | undefined>> }) {
  const params = await searchParams;
  const cookieStore = await cookies();
  const signedIn = cookieStore.has("exergi_session");
  const apiBase = process.env.EXERGI_API_BASE_URL;
  const state = params.shopify;
  return <MerchantPage eyebrow="Onboarding" title="Connect Shopify without giving up control" description="Exergi reads historical commerce data. It cannot change the store, create discounts, contact customers or spend budget.">
    {state === "connected" ? <div className="notice"><strong>Shopify connected.</strong><p>The read-only initial sync can now be started. No live result is claimed before reconciliation completes.</p></div> : null}
    {state === "error" ? <div className="notice warning"><strong>Shopify was not connected.</strong><p>{String(params.reason ?? "The authorization response could not be verified.")}</p></div> : null}
    <section className="product-panel onboarding-steps">
      <div className="health-row"><span>1. Exergi account</span><Status label={signedIn ? "SIGNED IN" : "SIGN IN REQUIRED"} tone={signedIn ? "good" : "partial"} /></div>
      <div className="health-row"><span>2. Shopify domain and permission review</span><Status label="READY" tone="good" /></div>
      <div className="health-row"><span>3. Historical read-only sync</span><Status label="AFTER OAUTH" tone="neutral" /></div>
      <div className="health-row"><span>4. Reconciliation and data readiness</span><Status label="NOT STARTED" tone="neutral" /></div>
      <div className="health-row"><span>5. First descriptive insight</span><Status label="DATA NOT READY" tone="neutral" /></div>
    </section>
    <section className="product-panel dashboard-section">
      <p className="section-kicker">Connect Shopify</p><h2>Enter the permanent shop domain</h2>
      <p>Use <code>your-store.myshopify.com</code>. Custom storefront domains are not accepted.</p>
      <form className="connect-form" method="get" action={apiBase ? `${apiBase.replace(/\/$/, "")}/api/v1/shopify/install` : undefined}>
        <label htmlFor="shop">Shop domain</label>
        <div><input id="shop" name="shop" type="text" placeholder="your-store.myshopify.com" required pattern="[A-Za-z0-9][A-Za-z0-9-]*\.myshopify\.com" /><button type="submit" disabled={!signedIn || !apiBase}>Connect Shopify</button></div>
      </form>
      {!apiBase ? <p className="form-note">Deployment configuration is incomplete. No placeholder connection is shown as successful.</p> : null}
    </section>
    <section className="product-panel dashboard-section"><h2>Permissions requested</h2><div className="scope-list"><code>read_orders</code><code>read_products</code><code>read_inventory</code><code>read_customers</code><code>read_returns</code></div><p>Customer names, email, phone and addresses are not queried. Older-than-default order history and Shopify Payments data remain separate approval gates.</p></section>
  </MerchantPage>;
}
