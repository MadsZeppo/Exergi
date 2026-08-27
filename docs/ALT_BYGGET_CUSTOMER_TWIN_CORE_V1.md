# Alt bygget — Customer Twin Core V1

## Kort konklusion

Vi har bygget den første egentlige produktkerne til en **Verified Customer Twin for Digital
Commerce**.

Kernen kan nu:

- indlæse og auditere rigtige commerce-transaktioner;
- bygge leak-safe kundetilstande på et bestemt historisk tidspunkt;
- identificere kundelivscyklusser og adfærdssegmenter;
- sammenligne simple og mere fleksible predictive modeller;
- skelne mellem individuel rangering og aggregate forecasting;
- forklare observerede revenue-ændringer med en eksakt matematisk decomposition;
- route naturlige kundespørgsmål til den korrekte matematiske engine;
- mærke hvert svar med den korrekte evidenstype;
- afvise unsupported causal-, discount- og profitpåstande;
- fryse predictions og senere tilføje realiserede resultater i Prediction Ledger.

Den samlede videnskabelige status er fortsat **FAIL** mod den fulde PASS-definition. Den praktiske
implementeringsstatus er **MIXED**. State-, Driver-, Query- og Evidence Safety-lagene fungerer, men
repeat-purchase-modellen er kun `RANKING_ONLY`, X5 er ikke valideret, og contribution profit samt
discount causality kan ikke beregnes fra de tilgængelige data.

## Produktarkitekturen

Den byggede kerne følger denne struktur:

```text
REAL COMMERCE DATA
        ↓
CANONICAL COMMERCE MODEL
        ↓
LIVING CUSTOMER STATE
        ↓
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
STATE / COHORT ENGINE
PREDICTION ENGINE
DRIVER ENGINE
ACTION / CAUSAL ENGINE
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
        ↓
ECONOMIC READINESS
        ↓
VERIFIED DECISION LAYER
        ↓
STRICT TWIN QUERY ENGINE
        ↓
EVIDENCE-BOUND ANSWER
        ↓
PREDICTION LEDGER
```

Vi byggede ikke Customer Population V4, en generativ simulator, LLM-kunder, Shopify OAuth, en UI
eller autonome actions.

## Det nye rigtige datasæt

Vi hentede den originale **Online Retail II**-fil direkte fra UCI Machine Learning Repository,
dataset ID 502.

| Felt | Resultat |
|---|---|
| Kilde | UCI Machine Learning Repository |
| DOI | `10.24432/C5CG6D` |
| Licens | CC BY 4.0 |
| Periode | 1. december 2009 – 9. december 2011 |
| Rækker | 1.067.371 |
| Identificerede kunder | 5.942 |
| Gyldige kundeordrer | 36.969 |
| Repeat customers | 4.255 |
| Historik | 738 dage |
| Positiv identificeret gross revenue | £17.743.429,18 |

SHA-256:

- ZIP: `572e36277c2390fbfde10664750731e0a86f55e33470d91919085f0408e67bfb`
- XLSX: `bcbe73b35f5b7babf197fb0cb983a11f5d9ff929078d4aa53d171b1f2df2e980`

Den rå XLSX bruger feltnavnene `Invoice`, `StockCode`, `Description`, `Quantity`, `InvoiceDate`,
`Price`, `Customer ID` og `Country`. De afviger lidt fra navnene på UCI-websiden. Vi bevarede den
faktisk observerede schema i provenance i stedet for at overskrive den med dokumentationsnavne.

## Streaming XLSX-ingestion

Repository’et havde ingen Excel-parserdependency. Derfor byggede vi en deterministisk streaming
XLSX-parser, der:

- læser begge worksheets direkte fra XLSX/XML;
- håndterer shared strings og Excel-datoer;
- skriver batches til komprimeret Parquet;
- bevarer rå transaktionssemantik;
- tilføjer eksplicit afledte felter som cancellation-status og line value;
- gemmer kilde-URL, DOI, licens, tidspunkt, schema og hashes.

Den processerede Parquet fylder cirka 7,7 MB og indeholder alle 1.067.371 rækker.

## Dataauditen

Vi analyserede invoice-semantik, cancellations, negative quantities, priser, identitet, dubletter,
lande, repeat customers og ekstreme baskets.

| Auditpunkt | Antal |
|---|---:|
| Cancellation-prefix-linjer | 19.494 |
| Negative-quantity-linjer | 22.950 |
| Zero-price-linjer | 6.202 |
| Negative-price-linjer | 5 |
| Linjer uden Customer ID | 243.007 |
| Eksakte dubletter ud over første forekomst | 34.335 |
| Lande | 43 |

Den fastlåste definition er:

- En ordre er ét ikke-annulleret invoice med Customer ID og mindst én gyldig positiv linje.
- Order value er summen af `Quantity × Price` over positive gyldige linjer.
- Cancellation-prefix og negative quantity rapporteres separat, fordi de ikke er identiske.
- Manglende Customer ID må ikke bruges til customer state eller repeat prediction.
- Ekstreme wholesale baskets slettes ikke lydløst.
- Revenue kaldes ikke profit.

## Canonical commerce contracts

Vi byggede typed kontrakter for:

- `Customer`
- `Product`
- `Order`
- `OrderLine`
- `Cancellation`
- `Refund`
- `CustomerEvent`
- `MarketingExposure`
- `ActionExposure`

Kontrakterne holder `observed_fields` og `derived_fields` adskilt. Overlap afvises ved validering.
Unavailable commerce-felter bliver ikke opfundet.

## LivingCustomerState

`LivingCustomerState` repræsenterer kunde `i` ved `as_of = T`. Kun information før `T` bruges til
features. Fremtidige outcomes beregnes i et separat labelvindue.

State indeholder blandt andet:

- pseudonymt customer ID og land;
- first seen og last seen;
- recency, frequency og monetary value;
- orders, revenue og units i 30/90/180-dages vinduer;
- AOV og median order value;
- customer age og interpurchase time;
- repeat rate og cadence change;
- product affinity, diversity og entropy;
- cancellation frequency og value;
- recent frequency-, revenue- og AOV-change;
- lifecycle;
- transaction support, history length, ESS og reliability.

Der er ikke blandet forecasts ind i observerede snapshot-metrics.

## Lifecycle og behavioral cohorts

Vi sammenlignede:

1. deterministiske lifecycle-regler;
2. KMeans med fire clusters som challenger.

| Metode | Adjacent-period stability |
|---|---:|
| Deterministisk lifecycle | 0,7663 agreement |
| KMeans challenger | 0,7593 adjusted Rand |

Den deterministiske metode blev valgt, fordi den både var lidt mere stabil og havde klare
transition-semantikker. Vi antog ikke, at clustering automatisk var bedre.

Observeret final 30-dages purchase rate:

| Cohort | Purchase rate |
|---|---:|
| Active | 46,0% |
| New | 32,1% |
| Cooling | 29,7% |
| Dormant | 11,8% |

Cohortbeskrivelser genereres mekanisk fra statistik. Der bruges ikke falske personas.

## Repeat-purchase tournament

Vi evaluerede sandsynligheden for køb i de næste 30 dage med kronologiske splits.

Sammenlignede modeller:

- population rate;
- simpel RFM;
- logistic regression;
- gradient boosting;
- empirical-Bayes purchase-rate challenger.

Logistic regression vandt development på Brier score og blev frosset før final reveal.

| Model | Development AUC | Development Brier | Final AUC | Final Brier | Final ECE | Buyer error |
|---|---:|---:|---:|---:|---:|---:|
| Population rate | 0,500 | 0,1625 | 0,500 | 0,1957 | 0,0562 | 21,58% |
| RFM | 0,753 | 0,1418 | 0,759 | 0,1689 | 0,0821 | 20,88% |
| Logistic | 0,761 | **0,1354** | 0,784 | 0,1537 | 0,0535 | 19,45% |
| Gradient boosting | 0,770 | 0,1355 | 0,785 | **0,1519** | 0,0549 | 21,09% |
| Empirical Bayes | 0,759 | 0,1436 | 0,772 | 0,1555 | **0,0247** | **9,40%** |

Den frosne logistic-model forventede 1.186,5 buyers mod 1.473 faktiske buyers.

Final status er derfor:

`RANKING_ONLY`

Modellen er nyttig til “hvem er mere sandsynlig?”, men ikke til fuldt kalibreret population
incidence.

Final-data ændrede ikke vinderen. Gradient boosting og empirical Bayes klarede sig bedre på nogle
final-metrics, men de blev ikke valgt efter reveal.

## BG/NBD-status

Vi implementerede ikke en falsk BG/NBD-approximation og kaldte den BG/NBD. Den relevante dependency
er ikke installeret, og en fuld antagelsesvalidering blev ikke afsluttet.

Status:

`NOT VALIDATED`

Det er en af grundene til, at Prediction Engine ikke kan få PASS.

## Monetary-value tournament

Vi estimerede conditional future order value blandt faktiske future buyers.

| Model | MAE | Median AE | Aggregate bias |
|---|---:|---:|---:|
| Global/cohort mean | £292,88 | £238,83 | +17,58% |
| Customer mean | £189,88 | **£102,40** | +1,48% |
| Shrunk customer mean | £217,78 | £156,62 | +12,12% |
| Gradient boosting | **£187,81** | £112,95 | -2,76% |

Customer mean vandt på den frosne primære medianfejl. Gradient boosting vandt på gennemsnitlig
absolute error.

Gamma-Gamma blev ikke anvendt uden validering af de nødvendige antagelser.

## Separat aggregate forecasting

Vi fastholdt V3-lektionen:

- Customer propensity svarer på **WHO**.
- Aggregate forecast svarer på **HOW MUCH**.

For buyers, orders og revenue sammenlignede vi:

- last period;
- trailing mean;
- weighted trailing mean;
- trend;
- exponential smoothing.

Last period vandt development for alle tre targets.

| Target | Frozen November forecast | Actual | Relative error |
|---|---:|---:|---:|
| Buyers | 1.364 | 1.664 | 18,03% |
| Orders | 1.929 | 2.657 | 27,40% |
| Revenue | £1.039.318,79 | £1.161.817,38 | 10,54% |

Customer propensity sums blev ikke brugt som aggregate forecast.

## Driver Engine

Vi byggede en symmetrisk Shapley-decomposition af identiteten:

```text
Revenue = Buyers × OrdersPerBuyer × RevenuePerOrder
```

September til oktober steg revenue med £86.480,41.

| Driver | Matematisk bidrag |
|---|---:|
| Buyer count | +£74.217,33 |
| Orders per buyer | +£19.889,91 |
| Revenue per order | -£7.626,83 |
| Reconciliation residual | £0,00 |

Dette er en eksakt accounting/statistical decomposition. Det kaldes ikke causal evidence.

## Evidenstyper

Følgende evidenstyper er implementeret:

- `OBSERVED_IDENTITY`
- `DESCRIPTIVE_DECOMPOSITION`
- `PREDICTIVE_ASSOCIATION`
- `CAUSAL_RCT`
- `CAUSAL_OBSERVATIONAL`
- `CONTEXT_ONLY`
- `INSUFFICIENT`

`EvidenceBoundAnswerRenderer` håndhæver forskellige formuleringer for hver type. Correlation,
feature importance og predictions må ikke omskrives til “X caused Y”.

## Twin Query Engine

Vi byggede:

- `TwinQuery`
- `TwinQueryPlan`
- `TwinAnswer`
- `EvidenceItem`
- `TwinQueryPlanner`
- `EvidenceBoundAnswerRenderer`

Query classes:

- DESCRIPTIVE
- CHANGE
- SEGMENT
- PREDICTIVE
- DRIVER
- CAUSAL
- SCENARIO
- DECISION

Plannerens output er en strict typed allowlist. Den genererer ikke fri SQL og kan ikke forespørge
rå tabeller vilkårligt.

Den faste query-suite indeholder 30 spørgsmål.

| Test | Resultat |
|---|---:|
| Korrekt intent routing | 30/30 — 100% |
| Korrekt evidence label | 30/30 — 100% |
| Unsupported causal-language violations | 0 |
| Ukendt spørgsmål | Fail closed til `INSUFFICIENT` |

## Action contracts

Vi byggede typed contracts for:

- `ActionDefinition`
- `ActionSpace`
- `ActionEvidence`
- `ActionEffectDistribution`

Action families:

- `TARGETED_COMMUNICATION`
- `OFFER`
- `DISCOUNT_DEPTH`
- `NO_ACTION`

Discount action er bounded, men kontrakten skaber ikke i sig selv causal evidence.

Online Retail II har ingen identificerbar discount assignment. Derfor er discount-status:

`NOT ENOUGH EVIDENCE`

## Criteo-integration

Det eksisterende unbiased Criteo-randomiserede benchmark er integreret i den fælles action-evidence
artefakt.

Det omfatter:

- 13.979.592 rækker;
- matched publisher hash;
- randomized binary treatment;
- intention-to-treat-evaluering;
- frozen-before-reveal predictions;
- S-, T-, X- og DR-learners samt simple challengers.

S-learner havde stærkest uplift calibration MAE på 0,0000821. Outcome propensity havde højeste
rapporterede AUUC på 0,003385. DRLearner er ikke gjort til automatisk default.

Criteo validerer et anonymiseret advertising action-response-lag. Det validerer ikke pricing,
profit, World State, merchant transfer eller præcise individuelle counterfactuals.

## X5-status

X5 RetailHero blev ikke hentet eller valideret. Vi antog ikke adgang eller brugsret til cirka 45
millioner transaktionsrækker uden en verificeret officiel acquisition path.

Status:

`NOT ACQUIRED OR VALIDATED`

Action Engine får derfor kun MIXED.

## Economic Engine

Vi byggede `EconomicOutcome` med eksplicitte felter for:

- revenue;
- COGS;
- discounts;
- refunds;
- shipping subsidies;
- action cost;
- contribution profit;
- missing fields og computation status.

Online Retail II indeholder ikke COGS eller action cost. Derfor er contribution profit:

`NOT COMPUTABLE — MISSING COGS/ACTION COSTS`

Revenue bliver aldrig præsenteret som profit.

## World State

Det eksisterende World State blev bevaret uden nye makrokilder.

Online Retail II er historisk UK-commerce. Repository’ets eksisterende aktuelle/amerikanske World
State er ikke geografisk og tidsmæssigt aligned.

Status:

`NOT AVAILABLE FOR THIS DATASET`

`StateInteractionEvidence` tillader kun “under current environment”-sprog med faktisk alignment og
validering. “Due to X” kræver causal evidence.

## Shopify mapping

Vi byggede en fremtidig Shopify-mappingcontract uden OAuth eller live integration.

Mappingen understøtter konceptuelt:

- pseudonymous Customer ID;
- Order;
- line items;
- refunds;
- products og variants;
- Web Pixel standard events.

Allowlistede behavioral events omfatter blandt andet:

- `page_viewed`
- `product_viewed`
- `product_added_to_cart`
- `product_removed_from_cart`
- `cart_viewed`
- `checkout_started`
- `checkout_completed`
- `search_submitted`
- `collection_viewed`

Kravet om adgang til ældre Shopify-orders er dokumenteret. Readiness skelner mellem
`TRANSACTION_ONLY` og `FULL_BEHAVIORAL`.

## Klaviyo mapping

Vi byggede mappingcontract for Klaviyo profile-, metric- og timestamp-events.

Events kan mappes til:

- `MarketingExposure`
- `CustomerEvent`
- `ActionExposure`

Email opens, email clicks og SMS clicks er engagement. De er ikke automatisk randomized treatment
assignment. Tests håndhæver denne forskel.

## Experiment infrastructure

`ExperimentDefinition` indeholder:

- experiment ID;
- action;
- randomization unit;
- eligibility rule;
- control og treatment;
- assignment probability;
- primary metric;
- guardrails;
- minimum detectable effect;
- planned sample size;
- start og slut.

Derudover er bygget:

- stabil SHA-256-baseret deterministic assignment;
- SRM-check;
- fail-closed trust ved SRM p-værdi under 0,01;
- A/A-understøttelse gennem samme assignment- og SRM-infrastruktur.

## Customer Twin readiness

Readiness rapporteres separat i stedet for som én misvisende confidence score.

| Capability | Status |
|---|---|
| Descriptive | READY |
| Predictive repeat purchase | LIMITED / RANKING_ONLY |
| Causal targeted campaign | LIMITED — benchmark, ikke merchant transfer |
| Discount causality | NOT READY |
| Contribution profit | NOT READY — missing COGS |
| World interaction | NOT READY — misaligned |
| Behavioral coverage | TRANSACTION_ONLY |

## Prediction Ledger

Ledgeren er udvidet med append-only Twin query/action records.

Ved prediction fryses:

- query ID;
- timestamp og as-of;
- typed query plan;
- snapshot- og modelversion;
- answer distribution;
- evidence type;
- validation status;
- action/treatment;
- incremental effect;
- economic estimate;
- decision state.

Senere kan realized outcome og calibration update tilføjes én gang. Frosne predictionfelter
overskrives ikke.

## Produktformede artefakter

Vi genererede:

- `artifacts/customer_twin_core_v1/product_demo.md`
- `artifacts/customer_twin_core_v1/product_demo.json`
- `artifacts/customer_twin_core_v1/frozen_selection.json`
- `artifacts/customer_twin_core_v1/frozen_final_purchase_probability.npy`
- `artifacts/customer_twin_core_v1/prediction_ledger.duckdb`

Demoen viser customer state, hvad der ændrede sig, 30-dages prediction, evidenstype, validation
status og actionmuligheder. Discount og profit fejler lukket.

## Nye og ændrede filer

### Source

- `src/commercial_twin/commerce_contracts.py`
- `src/commercial_twin/online_retail_ii.py`
- `src/commercial_twin/online_retail_twin.py`
- `src/commercial_twin/customer_twin_core.py`
- `src/commercial_twin/query_benchmark.py`
- `src/decision_engine/ledger/store.py`

### Scripts

- `scripts/prepare_online_retail_ii.py`
- `scripts/run_customer_twin_core_v1.py`

### Tests

- `tests/test_customer_twin_core_v1.py`

### Dokumentation

- `docs/ONLINE_RETAIL_II_DATA_AUDIT.md`
- `docs/CUSTOMER_TWIN_CORE_V1_REPORT.md`
- `docs/ALT_BYGGET_CUSTOMER_TWIN_CORE_V1.md`

### Data og provenance

- `data/raw/uci/online-retail-ii/online-retail-ii.zip`
- `data/raw/uci/online-retail-ii/online_retail_II.xlsx`
- `data/processed/uci/online-retail-ii/transactions.parquet`
- `data/processed/uci/online-retail-ii/provenance.json`

## Tests og kvalitet

Final repository-kvalitet:

| Check | Resultat |
|---|---|
| `ruff check .` | PASS |
| `mypy src` | PASS — 113 source files |
| `pytest -q` | PASS — 148 tests |

De nye tests dækker blandt andet:

- canonical field provenance;
- Shopify event allowlist;
- Klaviyo engagement versus treatment assignment;
- eksakt revenue decomposition;
- query routing og evidence labels;
- insufficient-evidence fallback;
- evidence-bound wording;
- causal World State wording;
- deterministic experiment assignment;
- SRM;
- experiment windows;
- discount fail-closed;
- bounded discount contract;
- ledger freeze og append-once outcome.

## Capability verdicts

| Engine | Verdict | Begrundelse |
|---|---|---|
| State Engine | PASS | Real data, canonical semantics, leak-safe state |
| Prediction Engine | FAIL | Final model er RANKING_ONLY; BG/NBD/Gamma-Gamma ikke valideret |
| Driver Engine | PASS | Eksakt zero-residual decomposition |
| Action Engine | MIXED | Criteo RCT findes; X5 og merchant transfer mangler |
| Economic Engine | FAIL | COGS og action costs mangler |
| Query Router | PASS | 30/30 korrekt |
| Evidence Safety | PASS | 0 unsupported causal-language violations |
| Integration Readiness | MIXED | Kontrakter findes, live connectors gør ikke |
| Customer Twin Core V1 samlet | **FAIL** | Den fulde videnskabelige PASS-gate er ikke opfyldt |

## Hvad kan ærligt bruges nu?

Som design-partnerprototype kan kernen bruges til:

- transaction audit og canonical mapping;
- observeret customer-state snapshot;
- lifecycle- og cohort-overblik;
- eksakt revenue-change decomposition;
- rangering af sandsynlige repeat buyers med `RANKING_ONLY`-label;
- typed query routing;
- evidenssikre svar;
- shadow-mode predictions og efterfølgende calibration;
- planlægning og ledgering af en første rigtig RCT.

## Hvad kan ikke ærligt sælges endnu?

- fuldt kalibrerede repeat-purchase forecasts på tværs af merchants;
- kausale kampagnepåstande uden merchantens egen randomisering;
- customer-level discount response;
- contribution-profit optimization uden økonomiske felter;
- World State-forklaringer på historisk UK-data;
- præcise individuelle counterfactuals;
- autonom `DO THIS` baseret på overført Criteo-evidens.

## Det præcise næste skridt

Det næste skridt er ikke Customer Population V4 eller mere simulation.

Det er:

1. forbind én designpartners historiske Shopify-transaktioner til den kanoniske adapter;
2. kør State, Driver og Prediction Engine i shadow mode;
3. mål out-of-time calibration på rigtige fremtidige outcomes;
4. preregistrer en lavrisiko customer-level A/A-test;
5. kør derefter en targeted-communication RCT;
6. brug deterministic assignment, SRM-gate og Prediction Ledger;
7. indsamle eksplicit campaign assignment, outcome og action cost;
8. tilføj COGS, hvis contribution profit skal beregnes;
9. start ikke discount optimization, før treatment/control og profitdata eksisterer.

## Endelig vurdering

Vi har nu en rigtig, testbar Customer Twin-kerne, der kan besvare observerede, predictive og
descriptive-driver-spørgsmål fra kode og rigtige data. Den kan skelne mellem evidenstyper og afvise
unsupported causal præcision.

Vi har ikke bevist, at hele Customer Twin-produktet kan give pålidelige action- og profitbeslutninger
for en rigtig merchant. Derfor er den korrekte samlede status stadig **FAIL**, med en brugbar
**MIXED** produktkerne og et konkret næste eksperiment.
