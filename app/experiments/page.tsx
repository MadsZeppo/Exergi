import { MerchantPage, Status } from "../merchant-shell";

export default function Page() {
  return <MerchantPage eyebrow="Experiments" title="Merchant-approved verification" description="Exergi does not launch tests or contact customers autonomously."><section className="product-panel"><div className="health-row"><span>Active randomized tests</span><Status label="NONE" tone="neutral" /></div><div className="health-row"><span>Assignment authority</span><Status label="NOT AVAILABLE" tone="partial" /></div><div className="health-row"><span>Outcome maturity</span><Status label="NOT AVAILABLE" tone="partial" /></div></section><div className="notice">A TEST decision is a proposal. It becomes an experiment only after a contract is preregistered and the merchant explicitly approves execution outside this read-only version.</div></MerchantPage>;
}
