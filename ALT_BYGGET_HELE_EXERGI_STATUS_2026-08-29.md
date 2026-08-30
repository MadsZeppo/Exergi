# Exergi — samlet status over alt bygget indtil nu

**Statusdato:** 29. august 2026

**Repository:** `/Users/madsflyvholm/Desktop/decision layer`

**GitHub:** `MadsZeppo/Exergi`

**Branch:** `main`

**Seneste immutable checkpoint:** `0a089ff1b1a73ba4cf6a1fd96c44a879f53aec3b`
**Dokumentets scope:** Hele Exergi/Verified Customer Twin/Commercial Twin/Decision Layer frem til og
med V7.3, inklusive videnskabelig kerne, Customer Twin, forecasting, causal inference, economics,
policy learning, experiments, safety, real-data audits, merchant shadow mode, API, frontend og
deployment.

## 1. Kort konklusion

Exergi er bygget som en evidensstyret e-commerce decision layer omkring denne mekanisme:

```text
Customer State
    → Opportunity
    → Action
    → Experiment
    → Observeret kausal og økonomisk respons
    → Merchant Memory
    → Bedre eller mere konservativ næste beslutning
```

Produktet er ikke bare en predictionsmodel. Repositoryet indeholder nu:

- leakage-sikker commerce- og customer-state-materialisering;
- probabilistisk forecasting og calibration;
- opportunity discovery og typed actions;
- diskrete og kontinuerlige causal estimators;
- development-only model tournaments;
- support-, overlap-, uncertainty- og claim-authority gates;
- contribution-profit economics og policy optimization;
- BAU, ACT, TEST, VERIFY, AVOID og ABSTAIN;
- experiment design, logged propensities og outcome maturity;
- Merchant Learning og historical-evidence matching;
- Prediction Ledger, model registry og one-time freeze/reveal patterns;
- store synthetic assurance-programmer;
- audits af Hillstrom, Buy Baits, Criteo, X5, Dunnhumby, H&M og andre datasets;
- read-only merchant shadow contracts;
- FastAPI, Streamlit research dashboard og en separat Next.js-produktflade.

Den vigtigste positive konklusion er, at Exergi har stærke mekanismer til leakage prevention,
cross-fitting, randomized evaluation, economics, support refusal og responsible BAU fallback.

Den vigtigste negative konklusion er, at systemet endnu ikke har dokumenteret en generelt sikker og
profitabel real-merchant action policy. V7.3 viste, at den eksisterende stability-gate er alt for
konservativ, men ingen testet erstatning opfyldte både safety og power. Ingen ny gate blev frosset,
Hillstrom blev ikke reassessed, og validation forblev lukket.

**Samlet ærlig status:** avanceret scientific decision-engine og read-only shadow-ready platform;
ikke et valideret autonomt commerce-produkt og ikke dokumenteret som real-world contribution-profit
engine.

## 2. Videnskabelige grundregler

Exergi holder fem spørgsmål mekanisk adskilt:

1. **Descriptive:** Hvad er observeret?
2. **Predictive:** Hvad forventes at ske?
3. **Causal:** Hvad ændres af en bestemt handling under eksplicitte antagelser?
4. **Economic:** Skaber handlingen incremental value efter alle deklarerede omkostninger?
5. **Decision:** Er evidensen stærk nok til at handle, teste, verificere, undgå eller vælge BAU?

De gennemgående regler er:

- prediction accuracy er ikke causal accuracy;
- revenue/spend er ikke contribution profit;
- ML-estimation og economic optimization er separate lag;
- synthetic oracle truth er evaluator-only;
- validation og sealed outcomes må ikke bruges til tuning;
- quick mode må ikke vælge officiel model eller åbne final targets;
- post-treatment features og mediatorer er forbudt;
- hidden confounding hævdes aldrig løst;
- unsupported action må aldrig blive ACT;
- BAU/Control er et korrekt og fuldt gyldigt output;
- et negativt resultat rapporteres som FAIL/INCONCLUSIVE frem for at blive tunet væk.

## 3. Samlet arkitektur

```text
Commerce events, transaktioner og merchant-data
                         ↓
             Data Trust og canonical contracts
                         ↓
       Point-in-time Customer/Company/World State
                         ↓
       Forecasting, support og reliability diagnostics
                         ↓
          Deterministisk Opportunity Discovery
                         ↓
       Begrænsede og typed Action Candidates
                         ↓
   Historisk randomiseret evidens + Merchant Memory
                         ↓
     Causal/DR estimation + uncertainty + support
                         ↓
             Contribution-profit economics
                         ↓
 ACT / TEST / VERIFY / AVOID / ABSTAIN / BAU-CONTROL
                         ↓
  Randomiseret assignment med kendte propensities
                         ↓
         Modnet kausal og økonomisk observation
                         ↓
        Prediction Ledger + learning records
                         ↓
           Næste beslutning og revalidering
```

Primære kodegrænser:

- `src/decision_engine/`: forecasting, causal, economics, policy, support og safety primitives;
- `src/commercial_twin/`: merchant/customer twin, learning, decision cards og shadow flows;
- `src/domains/commerce/`: commerce-specifikke actions og adapters;
- `benchmarks/`: versionsafgrænsede scientific assurance-programmer;
- `docs/`: audits, contracts og produktbeskrivelser;
- `artifacts/`: benchmark-, ledger- og modelresultater;
- `apps/`: Streamlit research dashboard;
- `app/` og `home.tsx`: separat Next.js-visningsprodukt.

## 4. Typed contracts og evidensroller

Der findes immutable Pydantic/dataclass-kontrakter for blandt andet:

- commerce events, orders, returns og costs;
- `ObservedCustomerState`, `CustomerState` og `MerchantCustomerTwin`;
- `CompanyState`, `WorldState`, `CommercialState` og `PopulationState`;
- opportunities, action candidates og decision cards;
- experiments, arms, assignments, propensities, outcomes og results;
- forecasts, uncertainty og calibration;
- causal estimates, support reports og policy values;
- `MerchantLearningRecord`;
- freeze manifests, model registry og Prediction Ledger;
- merchant shadow pilot rows og contribution-profit reconciliation.

Evidens er klassificeret som observed, descriptive, predicted, randomized causal, observational
causal, economic, simulated-only eller insufficient. Claim authority forhindrer, at et revenue- eller
proxy-resultat præsenteres som observeret contribution profit.

## 5. Data Trust og leakage-sikkerhed

Implementeret:

- event-, observation-, decision-, assignment- og outcome-maturity time;
- timezone-aware timestamps;
- point-in-time snapshots og cutoff-materialisering;
- chronological/group-safe splitting;
- expanding windows og rolling origin;
- strengt shiftede lag/rolling features;
- feature allowlists og post-treatment deny lists;
- cross-fitting uden training-row predictions;
- oracle isolation;
- frozen predictions før target reveal;
- data-, split-, source-, model-, config- og code hashes;
- one-time sealed guards og explicit quarantine records.

Quick mode er pipeline-QA alene. Officiel development selection, freeze og reveal kræver den fulde
preregistered procedure.

## 6. Customer, Company og World State

### Customer State

Customer State kan indeholde tenure, lifecycle, recency, frequency, monetary history, order count,
browsing/cart intent, cadence, category/product affinity, promotion history, refund/return behavior,
treatment history og support/reliability.

### Company State

Company State modellerer produkter, priser, COGS, margininput, inventory, campaigns, offers,
channels, shipping og fulfillment.

### World State

World State er timestamped ekstern kontekst med kilde/provenance, geography, confidence, calendar,
market og environment-signaler. Det er ikke en LLM-agentverden eller en påstået omniscient simulator.

### Full State versus RFM

Full Customer State er ikke empirisk bevist bedre end simple RFM-features. Flere benchmarks viste
ingen signifikant fordel, og V6 havde identisk economic policy value for FULL og RFM-only. Mere state
kompleksitet må derfor ikke sælges som værdi i sig selv.

## 7. Prediction Engine og customer behavior

Forecasting-laget indeholder:

- seasonal og simple baselines;
- LightGBM point- og quantile-modeller;
- quantile-crossing repair;
- conformal calibration;
- performance-vægtede ensembles;
- MAE, RMSE, WAPE, MASE og pinball loss;
- coverage, interval width, WIS og CRPS;
- subgroup- og drift-evaluering.

Customer-behavior-arbejdet omfatter dynamic state, event sequences, one-/multi-step prediction,
JDsearch behavioral/dynamics, RetailRocket research, H&M readiness og Customer Population Engine
V1–V3.

### H&M Day-1

Den officielle H&M-test omfattede 982.710 kunder og 31,8 mio. transaktionslinjer.

| Metric | Resultat |
|---|---:|
| AUROC | 0,7414 |
| ECE | 0,0471 |
| Buyer-count error | 20,90% |
| Top-10 lift | 2,70× |
| Observed transaction-value error | 39,28% |

Ranking havde signal, men calibration, aggregate buyer, subgroup og monetary gates fejlede. Status:
**ikke day-1 ready**.

### Customer Population Engine

V1–V3 byggede purchase incidence, conditional order count/value, new-customer arrivals, bottom-up
simulation, top-down forecasting, reconciliation, cohort/category fidelity og temporal calibration.
Mekanikken er omfattende, men en generelt kalibreret population simulator er stadig PARTIAL/FAIL.

## 8. Opportunity og Action Engines

Opportunity Engine finder blandt andet:

- repeat deterioration;
- high-intent/low-conversion;
- discount/margin leakage;
- return/refund leakage;
- cohort/funnel deterioration.

Gates omfatter minimum sample, baseline, persistence, economic materiality, uncertainty, data quality,
temporal validity og Benjamini–Hochberg false-discovery control.

Action taxonomy omfatter BAU, free shipping, shipping threshold, discount depth, targeted offer,
bundle, retention, merchandising og investigate/verify. Opportunity, audience, action, estimator og
economic objective holdes adskilt.

## 9. Diskret causal inference og model selection

Implementeret estimator- og diagnosticfamilie:

- raw difference in means;
- stratified estimates, ANCOVA og CUPED;
- S-, T-, X-, R- og DR-learners;
- cross-fitted AIPW;
- outcome models og two-part monetary models;
- random forest/extra trees/gradient/Tweedie challengers;
- causal forest og honest/DR policy tree;
- known/estimated propensity diagnostics;
- IPW, Hájek/SNIPS og doubly robust policy value;
- overlap, ESS, clipping, balance og falsification;
- development-only winner selection og freeze før later evaluation.

Commercial Twin antager ikke længere, at DR automatisk er standardvinder. Den empirisk bedst
kalibrerede/economically valuable model skal vælges pr. decision type på development-data.

## 10. Kontinuerlig discount dose-response

Continuous-treatment-programmet indeholder:

- truth-known retail DGP med measured/hidden confounding;
- naive, elasticity og flexible outcome baselines;
- `ContinuousDRDoseResponseEstimator`;
- strict chronological/group-safe cross-fitting;
- outcome nuisance `m(d,x)`;
- conditional density/GPS `f(d|x)`;
- kernel/localized doubly robust correction;
- density clipping, ESS og instability diagnostics;
- `ConditionalSupportGate`;
- blocked/clustered bootstrap uncertainty;
- calibration ved 50/80/90/95%;
- support-aware economic optimization;
- robust near-optimal action ranges;
- ACT/EXPERIMENT/ABSTAIN og falsification suite.

Kerneinvarianten er `unsupported optimum → ACT = 0`. De første definitive continuous benchmarks
fejlede causal recovery, calibration og abstention. Senere passes forbedrede implementationen, men
real observational continuous-discount readiness er ikke bevist, og hidden confounding er uløst.

## 11. Economics og policy optimization

Contribution profit kan indeholde:

```text
gross sales
− returns/refunds
− merchant-funded discounts
− COGS
− fulfillment/shipping cost
− payment fees
− campaign/action cost
```

Economics-laget understøtter expected/lower/upper value, margin/business constraints, risk-adjusted
utility, CVaR/expected shortfall, economic regret, robust near-optimal ranges og experiment cost/EVSI.

Estimatoren producerer en response distribution. Economics transformerer outcome til værdi.
Optimizeren vælger kun blandt supportede og tilladte actions. Flade profitkurver skal give et interval,
ikke falsk decimalpræcision.

## 12. Merchant Memory og closed-loop learning

En tidlig kernefejl var, at `MerchantLearningRecord` blev gemt uden at påvirke næste decision. Det er
rettet.

Historical Evidence matcher nu nye state/action-problemer til tidligere randomiseret evidens som:

- `HIGH_SUPPORT`;
- `PARTIAL_SUPPORT`;
- `STALE`;
- `OUT_OF_SUPPORT`.

Historisk evidens kan ændre næste recommendation til ACT, VERIFY, TEST eller AVOID. Mekanismen virker,
men flere Decision Lab-resultater viste, at memory kan ændre decisions uden automatisk at forbedre
profit. Closed-loop learning er derfor en implementeret mekanisme, ikke en generel value claim.

## 13. Experiment Engine og sequential safety

Experiment-laget indeholder typed specs, arms, eligibility, deterministic/random assignment, known
propensities, sample-size/power, assignment export, outcome maturity, contribution-profit outcome,
analysis og learning records.

Senere versioner tilføjede:

- anytime-valid promotion;
- committed-risk ledgers;
- merchant/family risk budgets;
- sentinel traffic;
- ACTIVE/WATCH/SUSPENDED/REVALIDATING/AVOID lifecycle;
- action leases og feedback clocks;
- drift, common-shock og causal-shift diagnostics;
- stop latency, drawdown, p95/p99 og CVaR metrics;
- no early release of immature risk.

Sikkerhedsmekanismerne er omfattende, men V7.1 og V7.3 dokumenterede fortsat uløste tradeoffs mellem
safety og power.

## 14. Prediction Ledger, registry og freeze/reveal

Implementeret:

- append-only DuckDB Prediction Ledger;
- frozen predictions før target reveal;
- evaluation records;
- append-only model performance registry;
- source/data/split/model/config/code hashes;
- immutable manifests;
- development/validation/sealed isolation;
- one-time reveal guards;
- JSON, Markdown, CSV og Parquet artifacts;
- deterministic seeds og common random numbers.

Historical FAILs bevares immutable. Et benchmark ændres ikke bagefter for at producere et grønt
resultat.

## 15. Real- og public-data audits

### Hillstrom

Hillstrom har tre randomiserede arms, known propensity og to-ugers `spend`. De otte lovlige
pretreatment fields er auditeret. `visit`, `conversion` og `spend` er outcome-only.

Hillstrom kan understøtte randomized spend/revenue og net revenue under en deklareret email-cost,
men ikke observeret contribution profit.

### Buy Baits

Den officielle `198781-V1.zip` blev verificeret med SHA-256
`3242238801aa40f5802e356d6a5d8cc108ccce9044be6586709017684a1642bc`. README, data og alle leverede
Stata scripts blev auditeret, og centrale Table 1/2-statistikker blev reproduceret.

Buy Baits er immutable klassificeret som:

```text
REAL_RANDOMIZED_ECONOMIC_NEGATIVE_CONTROL
incremental personalization = FAIL
responsible BAU abstention = PASS
```

Begrænsningerne er én legal pretreatment-feature, sparse purchases, heavy-tailed profit og ingen
stabil policy value over BAU. Validation/sealed må aldrig bruges til retuning.

### Criteo, X5 og Dunnhumby

- Criteo: randomized uplift/model-selection mechanics, men ikke monetary profit authority.
- X5 RetailHero: stærkt ranking-signal, men utilstrækkelig randomization/profit authority.
- Dunnhumby Complete Journey: observational backtest med svag overlap/ESS og manglende cost fields;
  status `INSUFFICIENT`.

### Dataset C

Der er søgt efter et tredje dataset med rigtig randomisering, row-level monetary outcome og mindst
fem pretreatment-features. Ingen kandidat er blevet mekanisk kvalificeret. Status:
`DATASET_C_NOT_FOUND`.

## 16. Benchmarkhistorik V1–V6.2

### Decision Lab V1–V2

V1 og V2 viste, at Learning Twin ikke automatisk slog Control eller Frozen Twin. I V2 var Learning
profit 113.899 mod Frozen 122.182 og Control 128.337. Full State slog ikke RFM. Status: **FAIL**.

### Decision Layer V3–V5

- V3: Learning slog Frozen men tabte til Control/random eligible; targeting var hovedfejlen.
- V4: cross-fitted DR action scores og Control fallback reducerede fejl, men Learning tabte stadig
  til Control.
- V5: VOI/ENBS reducerede exploration med 73%, men policyen tabte fortsat til Control.

### V6

V6 var første positive synthetic BAU-resultat: +206.070 total CP, +10,21% uplift og positiv paired
CI. Efter audit fandtes dog mindst 7,74% false ACT og 30,40% harmful individual exposure. Economic
value PASS; safe policy improvement FAIL.

### V6.1

V6.1 gav +370.626 CP mod BAU og reducerede false ACT til 5,08%, men missede `<1%`-kravet. Safety
forblev FAIL.

### V6.2

V6.2 fjernede post-observable/avoidable false ACT i Pack A og bevarede positiv value, men raw false
ACT, harmful exposure, tail drawdown, action capture og multi-pack robustness fejlede. Ingen freeze
eller official final reveal blev autoriseret.

## 17. V7 — customer-level economic policy

V7 kørte 57 development worlds på 19 families × 3 packs. Forest T-learner vandt development og blev
frosset før K/L/M.

| Metric | Resultat |
|---|---:|
| Mean held-out policy value | 0,6561 CP/customer |
| Positive-world value | 1,0218 CP/customer |
| Positive-world oracle capture | 98,88% |
| Unsupported ACT | 0 |
| Null/harmful ACT | 0% |

Personalization beyond best static bestod kun i 50% af heterogeneous validation worlds. Full
sequential tail-risk assurance var heller ikke gennemført, og freeze manglede source commit hash.
Final generalization blev ikke åbnet. Samlet V7-status: **FAIL**.

## 18. V7.1 — heterogeneity og sequential assurance

V7.1 adskilte material observable personalization fra nonmaterial og unobservable heterogeneity.
Qualitative heterogeneity var ofte observerbar; sparse heterogeneity var økonomisk nonmaterial på de
undersøgte packs.

Sequential assurance fejlede på stop latency og avoidable post-observable loss. Harmful, abrupt
reversal, causal shift og drift-scenarier havde væsentlig drawdown. Risk-budget invariants holdt, men
policyen stoppede for langsomt efter observerbar skade.

V7.1 gjorde produktet **READY FOR READ-ONLY SHADOW MODE**, ikke klar til aktiv merchant execution.

## 19. V7.2 — real randomized economic evidence

### Buy Baits checkpoint

Commit `1bd06ac` frøs Buy Baits som real randomized negative control. Development viste ingen stabil
personalization/static value over BAU, og abstention var korrekt. Raw data er ignored og immutable.

### Hillstrom development checkpoint

Commit `ac48997` etablerede den tre-armede development tournament. Best static var Mens Email, men
den interne 25% holdout gav net `+$0,735009`, SE `$0,511800`, CI
`[-$0,268100; +$1,738119]`. Ingen personalized policy slog static.

### Hillstrom forensic checkpoint

Commit `3ec8061` reproducerede alle 32.233 DEVELOPMENT rows og estimatorturneringen:

| Estimator | Gross uplift | Net ved $0,05 | Gross 95% CI |
|---|---:|---:|---:|
| Raw DIM | $0,738950 | $0,688950 | [$0,289414; $1,188486] |
| Stratified DIM | $0,732452 | $0,682452 | [$0,284402; $1,180502] |
| ANCOVA HC3 | $0,725803 | $0,675803 | [$0,277642; $1,173964] |
| CUPED | $0,737886 | $0,687886 | [$0,288500; $1,187273] |
| Cross-fitted AIPW | $0,724586 | $0,674586 | [$0,276670; $1,172502] |

Estimatorerne var enige, balance/assignment/overlap bestod, og den konservative adjusted net lower
bound var `+$0,226670`. Static freeze fejlede alligevel, fordi én af fem folds lå under `-$0,05` og
99%-winsorization mekanisk kappede alle outcomes til nul.

Hillstrom blev derfor `INCONCLUSIVE`; BAU blev valgt og validation forblev lukket.

### Hillstrom sealed-integritet

En tidligere headerdiagnostik viste en fuld raw row. Manifestet placerer row-0 i SEALED_TEST. Rækken
blev aldrig brugt til fitting eller scoring, men SEALED_TEST må aldrig omtales som fuldstændig urørt.
Rækken forbliver quarantined, splittene blev ikke flyttet, og VALIDATION er eneste mulige one-shot
confirmation.

## 20. V7.3 — stability-assurance continuation

V7.3 blev oprettet separat og låst i commit
`0a089ff1b1a73ba4cf6a1fd96c44a879f53aec3b`.

### Foldforensics

Den eksisterende V7.2-regel bruger fem unstratified deterministic SHA-256 folds. Den kræver fire af
fem positive folds, alle leave-one-fold-out positive og ingen fold under `-$0,05`.

Den negative Hillstrom-fold havde:

- 2.157 Mens og 2.250 Control;
- 20 purchases i hver arm;
- net DIM `-$0,160274`;
- SE `$0,477329`;
- CI `[-$1,095822; +$0,775274]`;
- alle fem leave-one-fold-out net estimates positive.

Det viser præcis, hvorfor én sparse/heavy-tailed fold kan veto et ellers positivt aggregate signal.
Forensics gav ikke tilladelse til at ændre gaten.

### Independent synthetic gate benchmark

V7.3 preregistrerede 10 world families × 500 development worlds og 11 gate-kandidater. Truth var
mekanisk evaluator-only. Unsupported ACT, budgetbrud og early release var nul for alle gates.

| Gate | Null ACT | Harmful ACT | Material ACT | False-negative rate |
|---|---:|---:|---:|---:|
| Existing V7.2 veto | 1,7% | 0,3% | 10,0% | 90,0% |
| Repeated stratified | 2,8% | 0,5% | 16,6% | 83,4% |
| Repeated balanced | 2,8% | 0,4% | 16,7% | 83,3% |
| Influence bounded | 2,5% | 0,3% | 19,1% | 80,9% |
| Bootstrap probability | 4,5% | 1,1% | 21,8% | 78,2% |
| Median of means | 7,6% | 1,5% | 24,3% | 75,7% |
| Cross-fitted AIPW LCB | 3,1% | 0,4% | 17,1% | 82,9% |
| Combined economic | 2,5% | 0,4% | 16,1% | 83,9% |

Den eksisterende gate har en uacceptabelt høj false-negative-rate. De eneste kandidater med den
preregistered ≥10 procentpoint forbedring fejlede safety: bootstrap harmful ACT var 1,1% over 1%-
grænsen, og median-of-means overskred både harmful og null limits.

Ingen gate blev valgt. Der blev ikke skrevet freeze artifact. Gate-validation og synthetic sealed
blev ikke åbnet. Buy Baits og Hillstrom blev ikke reassessed.

V7.3-slutstatus:

```text
V7_3_GATE_FAILED_HILLSTROM_NOT_REASSESSED
```

## 21. Merchant design-partner og shadow mode

Merchant-kontrakten kræver:

- stable unit/customer ID;
- assignment og eligibility timestamps;
- randomized assignment;
- known/logged propensity;
- timestamped pretreatment features;
- purchases og returns;
- revenue, discounts, COGS, fulfillment og payment fees;
- campaign/action cost;
- reconciled contribution profit;
- outcome maturity timestamp.

Protocol:

```text
Historical audit
  → preregistration
  → read-only shadow recommendations
  → explicit merchant approval
  → randomized test
  → matured contribution-profit evaluation
```

Autonomous shopændringer er forbudt. Missing costs, post-treatment features, immature outcomes,
duplicate units og propensity mismatch fejler lukket.

Aktuel readiness er **read-only shadow mode**. Der er ingen live connector/send path og ingen
autoriseret V7.3 ACT-gate.

## 22. Produkt-API, dashboard og frontend

### Backend/API

FastAPI-produktfladen eksponerer merchant-scoped state, opportunities, decision cards, evidence,
experiments og health/capability information. Videnskabelige labels og claim boundaries bevares.

### Research dashboard

Streamlit-dashboardet bruges til research inspection af forecasts, dose-response, uncertainty,
support, calibration, tournaments og synthetic/oracle comparisons. Synthetic resultater er mærket
som ikke-kommerciel evidens.

### Next.js frontend

Der er bygget en separat Exergi landing/product frontend med Decision Feed-eksempel, navigation og
Vercel-konfiguration. `npm run dev` og `npm run build` blev gjort mulige via root `package.json`.
Branding blev ændret fra Commercial Twin til `Exergi — Know what to do next`, og mindre UI-detaljer
som sidebar icons, connector line og CTA-arrow blev rettet.

Frontenden er en visnings-/marketingflade. Den er ikke evidens for den videnskabelige engine og må
ikke blandes sammen med benchmarkresultaterne.

## 23. Aktuel QA-status

Ved V7.3-checkpointet:

- focused V7.3/forensic QA: 40 tests bestået;
- full repository pytest: 429 tests bestået;
- Ruff: bestået;
- mypy: bestået på 180 source-filer;
- `git diff --check`: bestået;
- V7.3 freeze artifact: absent;
- validation opened: no;
- sealed opened: no.

## 24. Centrale immutable commits

| Commit | Betydning |
|---|---|
| `1bd06ac` | Buy Baits V7.2 negative-control checkpoint |
| `ac48997` | Hillstrom V7.2 development checkpoint |
| `3ec8061` | Hillstrom V7.2 forensic/stability checkpoint |
| `0a089ff` | V7.3 stability-assurance failure checkpoint |

Tidligere V6, V7 og V7.1 artifacts forbliver historiske og må ikke omskrives for at forbedre senere
resultater.

## 25. Capability matrix

| Capability | Aktuel status |
|---|---|
| Point-in-time state og leakage guards | IMPLEMENTED / TESTED |
| Forecasting og uncertainty primitives | IMPLEMENTED; dataset-afhængig calibration |
| Opportunity discovery | IMPLEMENTED; synthetic PASS på simple fixtures, mixed på svære worlds |
| Randomized ATE/ITT estimation | STRONG METHOD SUPPORT |
| Personalized policy over best static | IKKE GENERELT BEVIST |
| Continuous observational discount causality | RESEARCH / IKKE REAL-DATA READY |
| Conditional support/refusal | IMPLEMENTED / TESTED |
| Contribution-profit accounting | IMPLEMENTED; kræver komplette merchant costs |
| Merchant Memory affecting decisions | IMPLEMENTED |
| Prediction Ledger/freeze/reveal | IMPLEMENTED |
| Buy Baits responsible BAU abstention | PASS, immutable negative control |
| Hillstrom average spend uplift | POSITIV DEVELOPMENT SIGNAL |
| Hillstrom static decision freeze | INCONCLUSIVE |
| V7.3 replacement stability gate | FAIL; ingen gate valgt |
| Sequential risk control | MEKANISMER IMPLEMENTERET, GENERAL SAFETY UNPROVEN |
| Merchant shadow mode | READY, READ-ONLY |
| Autonomous merchant execution | FORBUDT / IKKE READY |
| Real merchant contribution-profit evidence | MISSING |
| Dataset C | NOT FOUND |

## 26. Hvad Exergi ærligt kan sige nu

Exergi kan sige:

- systemet kan bygge leakage-sikre customer/merchant states;
- systemet kan estimere og sammenligne randomized policy value;
- systemet kan bruge known/logged propensities og strict cross-fitting;
- systemet kan holde estimation, economics og decision gating adskilt;
- systemet kan afvise unsupported, immature eller economically incomplete actions;
- systemet kan anbefale BAU, TEST eller NOT ENOUGH EVIDENCE;
- Buy Baits viste korrekt responsible BAU abstention;
- Hillstrom DEVELOPMENT viser estimator-konsistent positiv Mens Email spend uplift;
- den nuværende stability-gate har lav power på sparse monetary outcomes;
- ingen testet replacement gate har endnu bestået den fælles safety/power-kontrakt;
- merchant shadow-data kan valideres read-only med komplet cost reconciliation.

## 27. Hvad Exergi ikke må påstå

Exergi må ikke sige:

- at produktet er production-ready til autonome shopændringer;
- at Hillstrom beviser contribution profit;
- at positive development results er independent validation;
- at SEALED_TEST er fuldstændig urørt;
- at personalization generelt slår static eller BAU;
- at Full State generelt slår RFM;
- at observational discount data identificerer causality uden antagelser;
- at hidden confounding er løst;
- at synthetic economic value er realized merchant profit;
- at en V7.3 gate er frosset eller klar til one-time validation.

## 28. Største resterende fejl

Den største aktuelle videnskabelige fejl er ikke manglende modelkompleksitet. Det er manglende bevis
for en gate, som både:

- har lav false ACT i null/harmful worlds;
- har nul unsupported ACT;
- begrænser tail downside;
- og samtidig har acceptabel power på sparse, heavy-tailed positive commerce effects.

Den gamle gate er for konservativ. De mere kraftfulde gates var ikke sikre nok. Det tradeoff er nu
målt, men ikke løst.

Derudover mangler:

- one-time independent Hillstrom validation authorization;
- et andet positivt real-randomized economic dataset;
- Dataset C med row-level money og flere legal pretreatment-features;
- real merchant shadow extract med komplette variable costs;
- merchant-approved randomized test;
- matured realized contribution-profit evaluation;
- dokumenteret sequential safety på relevante real operational paths.

## 29. Næste legitime evidenstrin

Det næste arbejde bør ikke være flere features eller frontend. Det bør være:

1. en ny, separat preregistered stability-method hypothesis—not retuning af V7.3;
2. uafhængig gate-development og validation med stærkere sparse-outcome inference;
3. ingen Hillstrom reassessment før en gate er frosset og uafhængigt valideret;
4. fortsat Buy Baits BAU negative-control protection;
5. read-only merchant shadow audit med komplet cost ledger;
6. kun derefter et merchant-approved randomized experiment;
7. contribution-profit evaluation først efter outcome maturity.

## 30. Endelig vurdering

Exergi er et usædvanligt omfattende og videnskabeligt disciplineret decision-engine repository. Det
har stærk engineering omkring temporalitet, causal estimation, economics, experiments, evidence
memory, support refusal, audit trails og immutable failure reporting.

Produktets styrke er ikke, at det altid siger ACT. Styrken er, at det kan skelne mellem signal,
support, uncertainty, economics og claim authority—og vælge BAU eller stoppe, når beviset ikke er
godt nok.

Det er den korrekte status efter V7.3: fundamentet er stærkt, flere komponenter er valideret på
syntetiske eller public randomized fixtures, men den samlede real-world commercial decision claim er
stadig ikke optjent.
