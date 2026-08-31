"use client";

import { useAuth } from "@clerk/nextjs";
import { FormEvent, useEffect, useState } from "react";

import { MerchantPage, Status } from "../merchant-shell";

type ConnectionState = "READY" | "CONNECTING" | "CONNECTED" | "SYNCING" | "DATA_NOT_READY" | "ERROR";
type AgreementStatus = { required_version: string; accepted: boolean; accepted_at: string | null };

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
  const [agreement, setAgreement] = useState<AgreementStatus | null>(null);
  const [agreementChecks, setAgreementChecks] = useState({ terms: false, privacy: false, dpa: false });
  const [accepting, setAccepting] = useState(false);
  const base = apiBase.replace(/\/$/, "");

  useEffect(() => {
    if (!isSignedIn || !base) return;
    let cancelled = false;
    void getToken().then(async (token) => {
      if (!token) throw new Error("Authentication token is unavailable.");
      const response = await fetch(`${base}/api/v1/shopify/agreements`, {
        headers: { Authorization: `Bearer ${token}` }, cache: "no-store",
      });
      if (!response.ok) throw new Error("Agreement status could not be verified.");
      if (!cancelled) setAgreement(await response.json() as AgreementStatus);
    }).catch((reason: unknown) => {
      if (!cancelled) setError(reason instanceof Error ? reason.message : "Agreement verification failed.");
    });
    return () => { cancelled = true; };
  }, [base, getToken, isSignedIn]);

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

  async function acceptAgreements() {
    if (!isSignedIn || !base || !agreement || !Object.values(agreementChecks).every(Boolean)) return;
    setAccepting(true);
    setError("");
    try {
      const token = await getToken();
      if (!token) throw new Error("Authentication token is unavailable.");
      const response = await fetch(`${base}/api/v1/shopify/agreements/accept`, {
        method: "POST",
        headers: { Authorization: `Bearer ${token}`, "Content-Type": "application/json" },
        body: JSON.stringify({ accepted: true, agreement_version: agreement.required_version }),
      });
      const body = await response.json() as AgreementStatus & { detail?: string };
      if (!response.ok || !body.accepted) throw new Error(body.detail ?? "Agreement acceptance failed.");
      setAgreement(body);
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "Agreement acceptance failed.");
    } finally {
      setAccepting(false);
    }
  }

  const authReady = isLoaded && isSignedIn;
  return <MerchantPage eyebrow="Onboarding" title="Connect Shopify without giving up control" description="Exergi reads historical commerce data. It cannot change the store, create discounts, contact customers or spend budget.">
    {["CONNECTED", "SYNCING", "DATA_NOT_READY"].includes(state) ? <div className="notice"><strong>Shopify connected.</strong><p>The read-only initial sync is {state === "SYNCING" ? "running" : "persisted"}. Metrics stay unavailable until reconciliation completes.</p></div> : null}
    {state === "ERROR" ? <div className="notice warning"><strong>Shopify was not connected.</strong><p>{error || "The authorization response could not be verified."}</p></div> : null}
    <section className="product-panel onboarding-steps">
      <div className="health-row"><span>1. Exergi account</span><Status label={authReady ? "SIGNED IN" : "SIGN IN REQUIRED"} tone={authReady ? "good" : "partial"} /></div>
      <div className="health-row"><span>2. Data-processing agreements</span><Status label={agreement?.accepted ? "ACCEPTED" : "ACCEPTANCE REQUIRED"} tone={agreement?.accepted ? "good" : "partial"} /></div>
      <div className="health-row"><span>3. Shopify domain and permission review</span><Status label={state === "CONNECTING" ? "AUTHORIZING" : state === "CONNECTED" ? "CONNECTED" : agreement?.accepted ? "CONNECT READY" : "BLOCKED"} tone={agreement?.accepted ? "good" : "neutral"} /></div>
      <div className="health-row"><span>4. Historical read-only sync</span><Status label={state === "SYNCING" ? "SYNCING" : "AFTER OAUTH"} tone={state === "SYNCING" ? "partial" : "neutral"} /></div>
      <div className="health-row"><span>5. Reconciliation and data readiness</span><Status label={state === "DATA_NOT_READY" ? "DATA NOT READY" : state === "READY" ? "READY" : "NOT VERIFIED"} tone={state === "READY" ? "good" : "neutral"} /></div>
    </section>
    {!agreement?.accepted ? <section className="product-panel dashboard-section">
      <p className="section-kicker">Required before Shopify Connect</p><h2>Review and accept the data terms</h2>
      <p>Acceptance is tied server-side to your verified workspace identity. No merchant identifier is submitted by this browser.</p>
      <div className="agreement-grid">
        <label><input type="checkbox" checked={agreementChecks.terms} onChange={(event) => setAgreementChecks((value) => ({ ...value, terms: event.target.checked }))} />I accept the current <a href="/terms" target="_blank">Terms of Service</a>.</label>
        <label><input type="checkbox" checked={agreementChecks.privacy} onChange={(event) => setAgreementChecks((value) => ({ ...value, privacy: event.target.checked }))} />I have reviewed the current <a href="/privacy" target="_blank">Privacy Policy</a>.</label>
        <label><input type="checkbox" checked={agreementChecks.dpa} onChange={(event) => setAgreementChecks((value) => ({ ...value, dpa: event.target.checked }))} />I am authorized to accept the current <a href="/dpa" target="_blank">Data Processing Addendum</a>. See also <a href="/subprocessors" target="_blank">Subprocessors</a>.</label>
        <button type="button" onClick={acceptAgreements} disabled={!agreement || accepting || !Object.values(agreementChecks).every(Boolean)}>{accepting ? "Recording…" : `Accept version ${agreement?.required_version ?? "…"}`}</button>
      </div>
      <p className="form-note">Founder-prepared documents pending qualified legal review. Legal entity, governing-law and notice details must be reviewed before commercial launch.</p>
    </section> : <div className="notice"><strong>Current agreements accepted.</strong><p>Version {agreement.required_version}, recorded {agreement.accepted_at ? new Date(agreement.accepted_at).toLocaleString() : "server-side"}.</p></div>}
    <section className="product-panel dashboard-section">
      <p className="section-kicker">Connect Shopify</p><h2>Enter the permanent shop domain</h2>
      <p>Use <code>your-store.myshopify.com</code>. Custom storefront domains are not accepted.</p>
      <form className="connect-form" onSubmit={connect}>
        <label htmlFor="shop">Shop domain</label>
        <div><input id="shop" name="shop" value={shop} onChange={(event) => setShop(event.target.value)} type="text" placeholder="your-store.myshopify.com" required pattern="[A-Za-z0-9][A-Za-z0-9-]*\\.myshopify\\.com" /><button type="submit" disabled={!authReady || !base || !agreement?.accepted || state === "CONNECTING"}>{state === "CONNECTING" ? "Connecting…" : "Connect Shopify"}</button></div>
      </form>
      {!base ? <p className="form-note">Deployment configuration is incomplete. No placeholder connection is shown as successful.</p> : null}
    </section>
    <section className="product-panel dashboard-section"><h2>Permissions requested</h2><div className="scope-list"><code>read_orders</code><code>read_products</code><code>read_inventory</code><code>read_customers</code><code>read_returns</code></div><p>Customer names, email, phone and addresses are not queried. Older-than-default order history and Shopify Payments data remain separate approval gates.</p></section>
  </MerchantPage>;
}
