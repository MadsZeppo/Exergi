import { DashboardState } from "../dashboard-state";
import { getShopifyDashboard } from "../lib/shopify-dashboard";
import { MerchantPage, Status } from "../merchant-shell";

export default async function Page() {
  const result = await getShopifyDashboard();
  if (result.state !== "ready") return <MerchantPage eyebrow="Decisions" title="Evidence before action" description="New merchants cannot receive DO from observational Shopify history."><DashboardState result={result} /></MerchantPage>;
  return <MerchantPage eyebrow="Decisions" title="Read-only decision cards" description="Scenario value is not causal or realized profit.">{result.data.decision_cards.length === 0 ? <div className="notice">NOT ENOUGH EVIDENCE — no decision card is ready.</div> : result.data.decision_cards.map(card => <article className="opportunity-card" key={card.id}><div><Status label={card.recommendation.replaceAll("_", " ")} tone={card.recommendation === "AVOID" ? "neutral" : "partial"} /><Status label={card.evidence_authority} tone="neutral" /></div><h2>{card.observation}</h2><p>{card.economic_significance}</p><dl><div><dt>Affected population</dt><dd>{card.affected_population}</dd></div><div><dt>Business as usual</dt><dd>{card.business_as_usual}</dd></div><div><dt>Possible action</dt><dd>{card.possible_action}</dd></div><div><dt>Downside</dt><dd>{card.downside}</dd></div></dl><h3>Why this decision?</h3><p>{card.uncertainty}</p><div className="reason-list">{card.reason_codes.map(reason => <code key={reason}>{reason}</code>)}</div><h3>What would change our view?</h3><ul>{card.what_changes_view.map(item => <li key={item}>{item}</li>)}</ul></article>)}</MerchantPage>;
}
