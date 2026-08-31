import { cookies } from "next/headers";

import { DashboardState } from "../dashboard-state";
import { getShopifyDashboard } from "../lib/shopify-dashboard";
import { MerchantPage } from "../merchant-shell";
import { DataIntegrationsClient } from "./data-integrations-client";

export default async function Page() {
  const result = await getShopifyDashboard();
  if (result.state !== "ready") {
    return <MerchantPage eyebrow="Data & integrations" title="Shopify connection" description="Read-only access, explicit permissions and observable sync state."><DashboardState result={result} /></MerchantPage>;
  }
  const shop = (await cookies()).get("exergi_shop")?.value ?? "";
  return (
    <DataIntegrationsClient
      apiBase={process.env.NEXT_PUBLIC_EXERGI_API_URL ?? ""}
      shop={shop}
      connection={result.data.connection}
      sync={result.data.sync}
      quality={result.data.data_quality}
    />
  );
}
