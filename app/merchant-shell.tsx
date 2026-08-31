import { UserButton } from "@clerk/nextjs";

const demoMode = process.env.NEXT_PUBLIC_EXERGI_DEMO_MODE === "true";

const nav = [
  ["Onboarding", "/onboarding"],
  ["Overview", "/overview"],
  ["Customers", "/customers"],
  ["Economics", "/economics"],
  ["Decisions", "/decisions"],
  ["Experiments", "/experiments"],
  ["Verification", "/verification"],
  ["Data & integrations", "/data-integrations"],
  ["Settings / security", "/settings/security"],
  ["Compliance", "/settings/compliance"],
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
        <div className="brand-mark">E</div>
        <div>
          <strong>Exergi</strong>
          <span>Commerce decision layer</span>
        </div>
        <nav>
          {nav.map(([label, href]) => (
            <a href={href} key={href}>{label}</a>
          ))}
        </nav>
        {demoMode ? <div className="demo-label">DEMO DATA<br />NOT COMMERCIAL EVIDENCE</div> : null}
      </aside>
      <section className="merchant-content">
        <header className="merchant-topbar">
          <span>{demoMode ? "Demo workspace" : "Read-only workspace"}</span>
          <code>{demoMode ? "DEMO DATA" : "SHOPIFY"}</code>
          <UserButton />
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
