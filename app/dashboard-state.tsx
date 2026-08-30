import type { DashboardResult } from "./lib/shopify-dashboard";

export function DashboardState({ result }: { result: DashboardResult }) {
  if (result.state === "ready") return null;
  return (
    <section className={`notice ${result.state === "error" ? "warning" : ""}`}>
      <strong>{result.state === "not_connected" ? "Authentication required" : "Data not ready"}</strong>
      <p>{result.detail}</p>
      <a className="primary-link compact" href="/onboarding">Open onboarding →</a>
    </section>
  );
}
