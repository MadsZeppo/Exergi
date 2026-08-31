import { ComplianceClient } from "./compliance-client";

export default function Page() {
  return <ComplianceClient apiBase={process.env.NEXT_PUBLIC_EXERGI_API_URL ?? ""} />;
}
