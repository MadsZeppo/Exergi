"use client";

import { useAuth } from "@clerk/nextjs";
import { FormEvent, useEffect, useState } from "react";

import { MerchantPage, Status } from "../merchant-shell";

type ConnectionState = "READY" | "CONNECTING" | "CONNECTED" | "SYNCING" | "DATA_NOT_READY" | "ERROR";

type Props = {
  apiBase: string;
  initialShop: string;
  oauthState: string;
  oauthReason: string;
};

export function OnboardingClient({ apiBase, initialShop, oauthState, oauthReason }: Props) {
  const { getToken, isLoaded, isSignedIn } = useAuth();
  const [shop, setShop] = useState(initialShop);
  const [state, setState] = useState<ConnectionState>(
    oauthState === "connected" ? "CONNECTED" : oauthState === "error" ? "ERROR" : "READY",
  );
  const [error, setError] = useState(oauthReason);
  const base = apiBase.replace(/\/$/, "");

  useEffect(() => {
    if (oauthState !== "connected" || !initialShop || !isSignedIn || !base) return;
    let cancelled = false;
    void getToken().then(async (token) => {
      if (!token) throw new Error("Authentication token is unavailable.");
      const response = await fetch(
        `${base}/api/v1/shopify/dashboard?shop=${encodeURIComponent(initialShop)}`,
        { headers: { Authorization: `Bearer ${token}` } },
      );
      if (!response.ok) throw new Error("The persisted Shopify state could not be verified.");
      const snapshot = await response.json() as {
        connection?: { status?: string };
        sync?: { status?: string };
        data_quality?: { status?: string };
      };
      if (!cancelled) {
        if (snapshot.connection?.status !== "CONNECTED") setState("ERROR");
        else {
          const context = await fetch("/api/shop-context", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ shop: initialShop }),
          });
          if (!context.ok) throw new Error("The dashboard shop context could not be saved.");
          if (["NOT_STARTED", "PENDING", "RUNNING"].includes(snapshot.sync?.status ?? "")) {
          setState("SYNCING");
          } else if (snapshot.data_quality?.status === "DATA_NOT_READY") {
            setState("DATA_NOT_READY");
          } else setState("READY");
        }
      }
    }).catch((reason: unknown) => {
      if (!cancelled) {
        setState("ERROR");
        setError(reason instanceof Error ? reason.message : "Connection verification failed.");
      }
    });
    return () => { cancelled = true; };
  }, [base, getToken, initialShop, isSignedIn, oauthState]);

  async function connect(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!isSignedIn || !base) return;
    setState("CONNECTING");
    setError("");
    try {
      const token = await getToken();
      if (!token) throw new Error("Authentication token is unavailable.");
      const response = await fetch(`${base}/api/v1/shopify/connect`, {
        method: "POST",
        headers: { Authorization: `Bearer ${token}`, "Content-Type": "application/json" },
        body: JSON.stringify({ shop }),
      });
      const body = await response.json() as { authorization_url?: string; detail?: string };
      if (!response.ok || !body.authorization_url) {
        throw new Error(body.detail ?? "Shopify authorization could not be started.");
      }
      window.location.assign(body.authorization_url);
    } catch (reason) {
      setState("ERROR");
      setError(reason instanceof Error ? reason.message : "Shopify authorization failed.");
    }
  }

  const authReady = isLoaded && isSignedIn;
  return <MerchantPage eyebrow="Onboarding" title="Connect Shopify without giving up control" description="Exergi reads historical commerce data. It cannot change the store, create discounts, contact customers or spend budget.">
    {["CONNECTED", "SYNCING", "DATA_NOT_READY"].includes(state) ? <div className="notice"><strong>Shopify connected.</strong><p>The read-only initial sync is {state === "SYNCING" ? "running" : "persisted"}. Metrics stay unavailable until reconciliation completes.</p></div> : null}
    {state === "ERROR" ? <div className="notice warning"><strong>Shopify was not connected.</strong><p>{error || "The authorization response could not be verified."}</p></div> : null}
    <section className="product-panel onboarding-steps">
      <div className="health-row"><span>1. Exergi account</span><Status label={authReady ? "SIGNED IN" : "SIGN IN REQUIRED"} tone={authReady ? "good" : "partial"} /></div>
      <div className="health-row"><span>2. Shopify domain and permission review</span><Status label={state === "CONNECTING" ? "AUTHORIZING" : state === "CONNECTED" ? "CONNECTED" : "CONNECT READY"} tone="good" /></div>
      <div className="health-row"><span>3. Historical read-only sync</span><Status label={state === "SYNCING" ? "SYNCING" : "AFTER OAUTH"} tone={state === "SYNCING" ? "partial" : "neutral"} /></div>
      <div className="health-row"><span>4. Reconciliation and data readiness</span><Status label={state === "DATA_NOT_READY" ? "DATA NOT READY" : state === "READY" ? "READY" : "NOT VERIFIED"} tone={state === "READY" ? "good" : "neutral"} /></div>
      <div className="health-row"><span>5. First descriptive insight</span><Status label={state === "READY" ? "READY" : "DATA NOT READY"} tone={state === "READY" ? "good" : "neutral"} /></div>
    </section>
    <section className="product-panel dashboard-section">
      <p className="section-kicker">Connect Shopify</p><h2>Enter the permanent shop domain</h2>
      <p>Use <code>your-store.myshopify.com</code>. Custom storefront domains are not accepted.</p>
      <form className="connect-form" onSubmit={connect}>
        <label htmlFor="shop">Shop domain</label>
        <div><input id="shop" name="shop" value={shop} onChange={(event) => setShop(event.target.value)} type="text" placeholder="your-store.myshopify.com" required pattern="[A-Za-z0-9][A-Za-z0-9-]*\\.myshopify\\.com" /><button type="submit" disabled={!authReady || !base || state === "CONNECTING"}>{state === "CONNECTING" ? "Connecting…" : "Connect Shopify"}</button></div>
      </form>
      {!base ? <p className="form-note">Deployment configuration is incomplete. No placeholder connection is shown as successful.</p> : null}
    </section>
    <section className="product-panel dashboard-section"><h2>Permissions requested</h2><div className="scope-list"><code>read_orders</code><code>read_products</code><code>read_inventory</code><code>read_customers</code><code>read_returns</code></div><p>Customer names, email, phone and addresses are not queried. Older-than-default order history and Shopify Payments data remain separate approval gates.</p></section>
  </MerchantPage>;
}
