import { auth } from "@clerk/nextjs/server";
import { cookies } from "next/headers";

export type CompanyState = {
  as_of: string;
  currency: string;
  order_count: number;
  customer_count: number;
  net_revenue: number;
  contribution_profit: number | null;
  repeat_revenue: number;
  refund_rate: number;
  discount_rate: number;
  lifecycle_distribution: Record<string, number>;
  economic_authority: string;
  completeness: Record<string, number>;
};

export type Diagnostic = {
  kind: string;
  title: string;
  observation: string;
  metrics: Record<string, string | number | null>;
  authority: string;
};

export type DecisionCard = {
  id: string;
  observation: string;
  economic_significance: string;
  affected_population: string;
  business_as_usual: string;
  possible_action: string;
  downside: string;
  data_basis: string[];
  uncertainty: string;
  evidence_authority: string;
  reason_codes: string[];
  recommendation: "TEST" | "AVOID" | "NOT_ENOUGH_EVIDENCE" | "BAU";
  assumptions: string[];
  what_changes_view: string[];
};

export type DashboardData = {
  connection: Record<string, unknown>;
  sync: Record<string, unknown>;
  company_state: CompanyState | null;
  diagnostics: Diagnostic[];
  decision_cards: DecisionCard[];
  data_quality: Record<string, unknown>;
};

export type DashboardResult =
  | { state: "ready"; data: DashboardData }
  | { state: "not_configured" | "not_connected" | "error"; detail: string };

export async function getShopifyDashboard(): Promise<DashboardResult> {
  const apiBase = process.env.NEXT_PUBLIC_EXERGI_API_URL;
  if (!apiBase) {
    return {
      state: "not_configured",
      detail: "The Exergi API has not been configured for this deployment.",
    };
  }
  const session = await auth();
  if (!session.userId) {
    return { state: "not_connected", detail: "Sign in before accessing merchant data." };
  }
  const token = await session.getToken();
  if (!token) return { state: "not_connected", detail: "Your session is no longer valid." };
  const shop = (await cookies()).get("exergi_shop")?.value;
  if (!shop) {
    return { state: "not_connected", detail: "Connect Shopify before accessing merchant data." };
  }
  try {
    const response = await fetch(
      `${apiBase.replace(/\/$/, "")}/api/v1/shopify/dashboard?shop=${encodeURIComponent(shop)}`,
      {
        headers: { Authorization: `Bearer ${token}` },
        cache: "no-store",
      },
    );
    if (!response.ok) {
      return { state: "error", detail: `Dashboard API returned ${response.status}.` };
    }
    return { state: "ready", data: (await response.json()) as DashboardData };
  } catch {
    return { state: "error", detail: "The Exergi API is currently unavailable." };
  }
}

export function money(value: number | null, currency: string): string {
  if (value === null) return "DATA NOT READY";
  return new Intl.NumberFormat("en", { style: "currency", currency }).format(value);
}
