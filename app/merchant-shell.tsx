const merchantId = "demo-merchant";

const nav = [
  ["Onboarding", "/onboarding"],
  ["Data health", "/data-health"],
  ["Customer base", "/customer-base"],
  ["Opportunities", "/opportunities"],
  ["Experiments", "/experiments"],
  ["Learning ledger", "/ledger"],
  ["Connections", "/settings/connections"],
];

export type MerchantPageProps = {
  eyebrow: string;
  title: string;
  description: string;
  children: React.ReactNode;
};

export function MerchantPage({ eyebrow, title, description, children }: MerchantPageProps) {
  return (
    <main className="merchant-app">
      <aside className="merchant-nav">
        <div className="brand-mark">VT</div>
        <div>
          <strong>Verified Twin</strong>
          <span>Merchant validation</span>
        </div>
        <nav>
          {nav.map(([label, href]) => (
            <a href={href} key={href}>{label}</a>
          ))}
        </nav>
        <div className="demo-label">SYNTHETIC DEMO<br />NOT COMMERCIAL EVIDENCE</div>
      </aside>
      <section className="merchant-content">
        <header className="merchant-topbar">
          <span>Demo Merchant</span><code>{merchantId}</code>
        </header>
        <div className="merchant-heading">
          <p>{eyebrow}</p>
          <h1>{title}</h1>
          <span>{description}</span>
        </div>
        {children}
      </section>
    </main>
  );
}

export function Status({ label, tone = "good" }: { label: string; tone?: string }) {
  return <span className={`status status-${tone}`}>{label}</span>;
}
