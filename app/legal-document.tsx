import documents from "../src/commercial_twin/shopify/compliance_documents.json";

type DocumentName = "privacy" | "terms" | "dpa" | "subprocessors";

export function LegalDocument({ name }: { name: DocumentName }) {
  const document = documents[name];
  return <main className="legal-page">
    <nav><a href="/">Exergi</a><span>Legal &amp; privacy</span></nav>
    <article>
      <p className="legal-status">{documents.review_status.replaceAll("_", " ")}</p>
      <h1>{document.title}</h1>
      <p className="legal-summary">{document.summary}</p>
      <dl className="legal-meta"><div><dt>Version</dt><dd>{documents.version}</dd></div><div><dt>Effective date</dt><dd>{documents.effective_date}</dd></div></dl>
      {document.sections.map((section) => <section key={section.heading}>
        <h2>{section.heading}</h2>
        {section.paragraphs.map((paragraph) => <p key={paragraph}>{paragraph}</p>)}
      </section>)}
      <aside><strong>Important legal status</strong><p>This document is founder-prepared and pending qualified legal review. It does not claim a certification or replace advice from qualified counsel.</p></aside>
    </article>
    <footer><a href="/terms">Terms</a><a href="/privacy">Privacy</a><a href="/dpa">DPA</a><a href="/subprocessors">Subprocessors</a></footer>
  </main>;
}
