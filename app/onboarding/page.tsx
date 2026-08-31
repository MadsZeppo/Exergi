import { OnboardingClient } from "./onboarding-client";

type Query = Record<string, string | string[] | undefined>;

function first(value: string | string[] | undefined): string {
  return Array.isArray(value) ? (value[0] ?? "") : (value ?? "");
}

export default async function Page({ searchParams }: { searchParams: Promise<Query> }) {
  const params = await searchParams;
  return (
    <OnboardingClient
      apiBase={process.env.NEXT_PUBLIC_EXERGI_API_URL ?? ""}
      initialShop={first(params.shop)}
      oauthState={first(params.shopify)}
      oauthReason={first(params.reason)}
    />
  );
}
