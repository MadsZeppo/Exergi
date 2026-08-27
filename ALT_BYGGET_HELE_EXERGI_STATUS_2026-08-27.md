# Exergi — samlet status over alt bygget indtil nu

**Statusdato:** 27. august 2026  
**Repository:** `/Users/madsflyvholm/Desktop/decision layer`  
**GitHub:** `MadsZeppo/Exergi`  
**Seneste commit på `main`:** `cbf895e`  
**Dokumentets scope:** Hele Exergi/Verified Customer Twin/Commercial Twin/Decision Layer, inklusive videnskabelig kerne, data, modeller, benchmarks, Merchant Learning, produkt-API, frontend og deployment.

## 1. Kort konklusion

Exergi er bygget som en videnskabelig e-commerce decision layer omkring denne kerne:

```text
Customer State
    → Opportunity
    → Action
    → Experiment
    → Observeret kausal og økonomisk respons
    → Merchant Memory
    → Bedre eller mere konservativ næste beslutning
```

Repositoryet indeholder nu:

- typed commerce- og beslutningskontrakter;
- point-in-time og leakage-sikker databehandling;
- customer-, company-, population- og world state;
- forecasting og probabilistisk usikkerhed;
- deterministisk opportunity discovery;
- causal/uplift modeltournaments;
- diskrete og kontinuerlige treatment-estimatorer;
- support-, overlap- og evidensgating;
- contribution-profit economics;
- ACT, TEST, VERIFY, AVOID, ABSTAIN og BAU/CONTROL;
- eksperimentdesign med loggede propensities;
- Merchant Learning, som påvirker efterfølgende beslutninger;
- Prediction Ledger, model registry, freeze/reveal og reproducerbare artifacts;
- syntetiske, semi-syntetiske, offentlige RCT- og observational benchmarks;
- FastAPI-produktflade;
- Next.js-visningsprodukt med 11 kompilerede routes;
- Vercel-konfiguration på `main`.

Den vigtigste positive konklusion er, at den frosne V6-benchmark for første gang slog en kompetent BAU-policy på usete syntetiske merchants med positiv merchant-paired confidence interval.

Den vigtigste negative konklusion er, at sikkerheden endnu ikke er god nok. V6 havde mindst 7,74% falske ACT-episoder efter audit. V6.1 reducerede dette til 5,08%, men fejlede grænsen på under 1%. V6.2 fjernede alle **undgåelige/post-observable** falske ACTs i Pack A, men fejlede fortsat raw harmful exposure og senere multi-pack robustness. V6.2 blev derfor ikke frosset, final targets blev ikke åbnet, og real-world validation blev ikke startet.

**Samlet ærlig status:** stærk forsknings- og beslutningsplatform, dokumenteret syntetisk økonomisk værdi, men ikke et valideret autonomt real-merchant produkt.

## 2. Videnskabelig grundregel

Produktet adskiller fem spørgsmål:

1. **Descriptive:** Hvad er observeret?
2. **Predictive:** Hvad forventes at ske?
3. **Causal:** Hvad ændres af en bestemt handling under eksplicitte antagelser?
4. **Economic:** Skaber handlingen incremental contribution profit efter omkostninger?
5. **Decision:** Er evidensen stærk nok til at handle, teste, verificere, undgå eller vælge BAU?

Det betyder blandt andet:

- prediction accuracy er ikke causal accuracy;
- revenue er ikke contribution profit;
- en ML-model må ikke direkte erklære en handling optimal;
- estimation og økonomisk optimering er separate lag;
- syntetisk oracle truth er evaluator-only;
- hidden confounding hævdes ikke løst;
- manglende support medfører refusal, ikke falsk præcision;
- CONTROL/BAU er et legitimt og ofte korrekt produktoutput;
- quick mode må kun validere pipelines, aldrig vælge officiel vinder eller afsløre final targets.

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

De centrale kodegrænser er:

- `src/decision_engine/`: generiske videnskabelige primitives;
- `src/commercial_twin/`: commercial/customer twin, merchant flows og præsentationskontrakter;
- `src/domains/commerce/`: commerce-actions og behavior adapters;
- `benchmarks/`: versionslåste videnskabelige tests;
- `artifacts/`: predictions, summaries, ledgers og benchmarktabeller;
- `apps/`: research dashboard;
- `app/` og `home.tsx`: Next.js-visningsprodukt.

## 4. Datakontrakter og typed objekter

Repositoryet har immutable Pydantic-kontrakter for blandt andet:

- commerce events og canonical order semantics;
- `ObservedCustomerState` og `MerchantCustomerTwin`;
- `CustomerState`, `CompanyState`, `WorldState` og `CommercialState`;
- `PopulationState`;
- `Opportunity` og `ActionCandidate`;
- `DecisionProblem`, `DecisionCard` og dispositions;
- `ExperimentSpec`, arms, assignments, outcomes og results;
- `MerchantLearningRecord`;
- forecasts og outcome distributions;
- causal estimates, uncertainty og support reports;
- policy value, economic regret og calibration;
- model selection, registry- og benchmarkrecords.

Evidensroller er adskilt som blandt andet:

- observed/descriptive;
- predictive;
- randomized causal;
- observational causal;
- economic;
- synthetic/simulated;
- insufficient evidence.

## 5. Data Trust, temporalitet og leakage-sikkerhed

Implementeret:

- eksplicit event time, observation time, decision time og action time;
- timezone-aware timestamps;
- point-in-time featurematerialisering;
- cutoff-baserede snapshots;
- halvåbne target-vinduer;
- expanding-window og rolling-origin evaluering;
- kronologiske og group-safe folds;
- strengt shiftede lag- og rolling-features;
- blokering af post-treatment features og mediatorer;
- feature allowlists;
- oracle isolation;
- frozen predictions før target reveal;
- data-, state-, config- og prediction-hashes;
- one-time final reveal-markører.

Der er testdækning for leakage, cross-fitting, oracle isolation og reproducerbarhed.

## 6. Customer State, Company State og World State

### Customer State

Customer State kan indeholde:

- tenure og lifecycle;
- recency, frequency og monetary value;
- ordre- og købshistorik;
- browsing, cart og checkout intent;
- recent intent og cadence;
- category/product affinity;
- promotion exposure og historical response;
- refund- og returnhistorik;
- treatment count og tid siden seneste treatment;
- support og reliability.

### Company State

Company State dækker typed produkt- og merchantforhold som:

- produkter og priser;
- COGS og margininput;
- inventory;
- campaigns og offers;
- channels;
- shipping og fulfillment.

### World State

World State indeholder tidsstemplet ekstern kontekst med:

- kilde og provenance;
- geografi;
- confidence;
- market-, calendar- og environment-signaler.

World State kan påvirke outcome i de syntetiske fixtures, men er ikke en AI-agentverden eller en påstået omniscient simulator.

### Full State versus RFM

På tværs af de seneste policybenchmarks er Full Customer State ikke bevist bedre end simple RFM-features. I V6 var FULL og RFM-only præcis ens i økonomisk policy value. Produktet må derfor ikke påstå, at mere state-kompleksitet i sig selv skaber værdi.

## 7. Prediction Engine og customer behavior

Forecasting-laget indeholder:

- sæsonbaselines;
- deterministiske LightGBM point models;
- quantile models;
- quantile-crossing repair;
- split-conformal calibration;
- historisk performance-vægtede ensembles;
- MAE, RMSE, WAPE, MASE og pinball loss;
- coverage, interval width, WIS og empirisk CRPS;
- drift- og subgroup-evaluering.

Behavioral/dynamic work omfatter:

- living/dynamic customer state;
- event sequence og dynamics models;
- one-step og multi-step prediction;
- JDsearch behavioral og dynamics benchmarks;
- RetailRocket research;
- H&M Day-1 readiness;
- Customer Population Engine V1, V2 og V3.

### H&M Day-1

Den officielle H&M-test omfattede 982.710 eksisterende kunder og 31,8 mio. transaktionslinjer.

| Metric | Resultat |
|---|---:|
| AUROC | 0,7414 |
| ECE | 0,0471 |
| Buyer-count error | 20,90% |
| Top-10 lift | 2,70× |
| Observed transaction-value error | 39,28% |

Ranking havde signal, men calibration-, aggregate buyer-, subgroup- og monetary-gates bestod ikke. Verdict: **NO til day-1 readiness**.

### Customer Population Engine

V1–V3 byggede og auditerede:

- purchase incidence;
- conditional order count;
- conditional order value;
- new-customer arrivals;
- bottom-up customer simulation;
- top-down forecasting;
- hierarchical reconciliation;
- cohort/category fidelity;
- temporal calibration;
- uncertainty og Prediction Ledger snapshots.

Der er reel læring og detaljeret failure analysis, men kalibreret population simulation er ikke generelt demonstreret. Dette lag er fortsat forskningsmæssigt **PARTIAL/FAIL**, afhængigt af capability.

## 8. Opportunity Engine

Opportunity Engine er deterministisk og økonomisk prioriteret. De fem hovedfamilier er:

1. Repeat deterioration.
2. High-intent / low-conversion.
3. Discount / margin leakage.
4. Return / refund leakage.
5. Cohort / funnel deterioration.

Opportunities kræver blandt andet:

- minimum sample size;
- legitim historisk baseline;
- persistence;
- minimum rate- og economic gap;
- uncertainty;
- data quality;
- temporal validity;
- Benjamini–Hochberg false-discovery control.

Et planted discovery-benchmark med seks merchant-typer og 240 merchants gav 100% precision, recall, economic-weighted precision/recall og Top-1 accuracy samt 0% null false positives. Det er en PASS på en klart separeret syntetisk fixture, ikke real-world bevis.

Nyere V6–V6.2 benchmarks viser, at rank-one discovery fortsat er svagere i komplekse verdener. V6 P@1 var 21,29%. V6.1 nåede 31,67% på sin officielle fixture, men fejlede economic-weighted precision. V6.2 Pack A havde omtrent 22–23% P@1 med stærkere P@3 og economic-weighted precision. Den forsvarlige produktclaim er derfor “top tre muligheder værd at undersøge”, ikke “øverste opportunity er altid korrekt”.

## 9. Action Candidates og Decision Cards

Den afgrænsede action taxonomy omfatter:

- BAU/Control/no action;
- free shipping;
- shipping-threshold adjustment;
- discount-depth adjustment;
- targeted offer;
- bundle/multi-buy;
- retention treatment;
- merchandising/category intervention;
- investigate/verify.

Action Candidate Engine holder opportunity, målgruppe og handling adskilt. Decision Cards samler:

- opportunity og economic gap;
- state og support;
- evidens og uncertainty;
- candidate actions;
- disposition;
- begrundelser;
- eventuelt experiment plan.

## 10. Causal inference for diskrete actions

Implementeret estimator- og diagnosticfamilie:

- difference in means;
- naive og outcome-regression baselines;
- S-, T- og X-learners;
- DRLearner og cross-fittet AIPW;
- R-learner og honest-forest challengers i relevante tournaments;
- known randomized propensities;
- propensity overlap, balance, clipping og ESS;
- direct, IPW, SNIPS og DR off-policy evaluation;
- treatment-shuffle placebo;
- sensitivity analysis og estimator disagreement;
- development-only model selection;
- freeze før untouched test.

Commercial Twin antager ikke længere, at én DR-model altid er standardvinder. Modeller sammenlignes pr. decision type, og officiel konfiguration må kun vælges på development-data.

### Hillstrom RCT

64.000 randomiserede rækker viste positive email-effekter, men learned policy slog ikke bedste statiske treatment. Personaliseret uplift-værdi blev derfor ikke demonstreret. Verdict: **MIXED**.

### Layer 3 synthetic AIPW

På randomized, measured-confounded og placebo-scenarier gav den cross-fittede AIPW-pipeline meget lav randomized bias, klar forbedring over naive estimation under measured confounding, cirka nominal coverage og forventelig placebo-fejlrate. Verdict: **PASS som syntetisk metodevalidering**.

### Criteo

Criteo blev brugt til randomized uplift/model-selection research. Resultaterne understøttede modeltournament og rankingdiagnostics, men kundevendt DO THIS-gating måtte ikke aktiveres uden økonomisk policy value mod simple alternativer.

### X5 RetailHero

V5 materialiserede 200.039 labeled train customers, 400.162 client rows og 45.786.568 pre-communication purchase lines med verificerede checksums. Cross-fitted DR-learner vandt development-turneringen og gav på intern final:

- AUUC 532,12;
- Qini 112,35;
- Top-10 uplift 0,1049;
- shuffle Qini −23,53.

Assignment var ikke dokumenteret som randomiseret, og data manglede contribution-profit outcomes. Verdict: **PARTIAL ranking evidence, ingen real profit evidence**.

### Dunnhumby Complete Journey

Dunnhumby-backtesten var observational, havde svag overlap/ESS og manglede cost fields. Adjusted ATE havde interval over nul. Resultatet var **INSUFFICIENT**, ikke en causal commercial claim.

## 11. Kontinuerlig discount dose-response

Repositoryet indeholder en fuld forskningspipeline for kontinuerlig discount:

- truth-known retail DGP;
- measured og hidden confounding;
- good, weak og bad support;
- naive, elasticity og flexible outcome baselines;
- `ContinuousDRDoseResponseEstimator`;
- kronologisk/group-safe cross-fitting;
- outcome nuisance `m(d,x)`;
- conditional treatment density `f(d|x)`;
- localized/kernel doubly robust correction;
- density floor og clipping;
- clipped fraction, weight og ESS diagnostics;
- `ConditionalSupportGate`;
- blocked/clustered bootstrap uncertainty;
- calibration ved 50/80/90/95%;
- support-aware economic optimization;
- robust near-optimal range;
- ACT / EXPERIMENT / ABSTAIN;
- placebos, specification variation og sensitivity.

Kerneinvarianten er:

```text
Unsupported optimum → ACT = 0
```

De første definitive continuous-retail resultater fejlede causal recovery, interval calibration og abstention. Senere DR- og support-passes forbedrede mekanismerne, men der er stadig intet bevis for real observational continuous-discount readiness. Hidden confounding er eksplicit uløst.

## 12. Conditional support og refusal

Support er kontekstspecifik, ikke blot “findes denne discount i datasættet?”. Gate-laget anvender blandt andet:

- conditional treatment density;
- local effective sample size;
- kernel-weighted support;
- nærmeste dose-distance;
- overlap relativt til træningspopulationen;
- extrapolation distance;
- nuisance-model disagreement.

Systemet kan derfor returnere:

- `ACT` ved supporteret, stabil og økonomisk meningsfuld evidens;
- `EXPERIMENT`/`TEST` ved interessant men utilstrækkelig evidens;
- `VERIFY` ved stale, konfliktende eller delvist relevant evidens;
- `AVOID` ved understøttet negativ økonomisk effekt;
- `ABSTAIN` ved alvorlig identifikations- eller supportfejl;
- `CONTROL`/`BAU` når upside ikke er dokumenteret.

## 13. Counterfactual uncertainty og calibration

Implementeret:

- quantile uncertainty;
- conformal calibration;
- blocked/clustered bootstrap over causal pipeline;
- intervals for response og profit;
- standard error og valid replicate count;
- coverage, width, calibration error og WIS;
- support- og dose-region diagnostics;
- Monte Carlo economic propagation;
- risk-adjusted utility og lower-tail CVaR/expected shortfall.

V6 what-if calibration bestod de frosne syntetiske kriterier:

| Metric | V6 |
|---|---:|
| Brier score | 0,135 |
| 95% interval coverage | 86,68% |
| Probability calibration error | 0,090 |
| Sign accuracy | 83,52% |
| Magnitude MAE | 0,271 |

Den højeste confidence-bucket var stadig overconfident. Syntetisk calibration beviser ikke real-world calibration.

## 14. Economics og policy optimization

Contribution profit kan inkludere:

```text
sales
− COGS
− discount
− shipping subsidy
− refunds/returns
− payment cost
− variable campaign cost
```

Economics-laget understøtter:

- expected contribution profit;
- lower/upper profit intervals;
- margin- og business constraints;
- risk-adjusted utility;
- lower-tail CVaR/expected shortfall;
- economic regret;
- robust near-optimal action ranges;
- experiment cost og exploration regret;
- baselines som treat-all, treat-none, simple merchant policy og BAU.

I V3 slog profitoptimering revenueoptimering med +10.386,28, 95% CI `[+9.723,50; +11.102,00]`. Dette viste, at økonomisk objective mattered på den syntetiske fixture.

## 15. Merchant Memory og closed-loop learning

En tidligere central fejl var, at `MerchantLearningRecord` blev gemt uden at ændre den næste decision. Det blev rettet.

`MerchantLearningRecord` kan indeholde:

- pre-action state;
- action og outcome definition;
- estimated causal effect;
- confidence interval og uncertainty;
- economics;
- evidence type;
- experiment ID og timestamp.

`HistoricalEvidenceMatcher` klassificerer evidens som:

- `HIGH_SUPPORT`;
- `PARTIAL_SUPPORT`;
- `STALE`;
- `OUT_OF_SUPPORT`.

Historisk randomiseret evidens påvirker derefter næste disposition. Mekanismen er implementeret og testet. Tidlige Decision Lab-resultater viste dog, at memory kunne ændre decisions uden at forbedre profit. Senere V3–V6-lag tilføjede sikrere policy learning, hierarki, lifecycle og driftkontrol.

## 16. Experiment Engine

Experiment-laget omfatter:

- typed experiment specs og arms;
- power/sample-size beregning;
- frozen assignment plans;
- deterministisk/randomiseret assignment;
- kendte og loggede propensities;
- batch- og outcome maturity;
- contribution-profit outcome;
- analyse og learning record;
- direct test cost;
- value of information;
- anytime-valid promotion;
- sentinel-, monitoring- og revalidation-traffic.

V5 tilføjede EVSI/ENBS:

```text
ENBS = future-population EVSI
       − direct experiment cost
       − expected experiment regret
```

TEST kræver derfor ikke blot uncertainty, men positiv konservativ expected net benefit of sampling.

## 17. Prediction Ledger, registry og freeze/reveal

Implementeret:

- append-only DuckDB Prediction Ledger;
- frozen predictions før target reveal;
- evaluation records;
- append-only model performance registry;
- model/config/state/prediction hashes;
- development-only tournaments;
- frozen winner/configuration;
- one-time official reveal markers;
- JSON, Markdown, CSV og Parquet artifacts;
- deterministic seeds og common random numbers;
- immutable historiske benchmarkartefakter.

Quick mode må:

- validere materialisering;
- validere leakage guards;
- kontrollere at alle modeller kører;
- vise provisional development diagnostics.

Quick mode må ikke:

- vælge officiel vinder;
- skrive officiel freeze;
- åbne final targets;
- skrive frozen final predictions;
- markere official final som revealed.

V6.2 følger dette fail-closed: freeze blev bevidst forsøgt og korrekt afvist, fordi development gates fejlede.

## 18. Benchmarkhistorik

### Decision Lab V1

- 15 verdener, 50 seeds pr. verden;
- Twin tabte til bedste baseline;
- closed-loop learning blev ikke demonstreret;
- verdict: **FAIL**.

### Decision Lab V2

| Policy | Profit |
|---|---:|
| Learning Twin | 113.899,21 |
| Frozen Twin | 122.182,32 |
| Control | 128.336,61 |

Learning tabte til både Frozen og Control. Full State versus RFM var ikke signifikant. Verdict: **FAIL**.

### E-commerce Decision Layer V3

| Policy | Profit |
|---|---:|
| Control | 128.613,54 |
| Merchant heuristic | 113.712,50 |
| Frozen | 122.304,24 |
| Learning | 124.098,78 |
| Random opportunity learning | 128.854,79 |
| Oracle reference | 132.347,79 |

Learning slog Frozen, men tabte til Control og random eligible. Opportunity → Audience → Action var den vigtigste fejl. Verdict: **FAIL**.

### E-commerce Decision Layer V4

V4 indførte cross-fittede DR action-scores, held-out policy learning, Control fallback og separat heterogeneity gate.

| Policy | Profit |
|---|---:|
| Control | 86.410,02 |
| Merchant heuristic | 76.251,14 |
| Random eligible | 80.817,23 |
| V3 frozen | 82.244,34 |
| V4 Learning | 83.517,84 |

V4 slog V3 og random eligible, havde 0% false ACT, men tabte til Control med −2.892,19, CI fuldt under nul. Verdict: **FAIL på samlet økonomisk value**.

### E-commerce Decision Layer V5

V5 tilføjede real-retail response audit, Open Bandit OPE, anytime-valid promotion og VOI-gating.

| Policy | Mean cumulative CP |
|---|---:|
| Control | 69.513,69 |
| V4 frozen | 50.980,27 |
| V5 uden VOI | 67.289,69 |
| V5 med VOI | 69.092,12 |

V5 med VOI reducerede exploration assignments med 73%, men tabte stadig til Control med −421,56, 95% CI `[-446,19; -397,12]`. Ingen horizon ved 12, 26 eller 52 episoder nåede breakeven. Verdict: **FAIL på exploration economics**.

### E-commerce Decision Layer V6

V6 var det første officielle positive BAU-resultat:

| Metric | Resultat |
|---|---:|
| V6 FULL − BAU total | +206.069,58 |
| Mean gain pr. merchant | +7.359,63 |
| Merchant-paired 95% CI | `[+3.007,31; +13.021,76]` |
| Relative uplift | +10,21% |
| Unseen merchants | 28 |
| Learning breakeven | Episode 2 |
| Unsupported ACT | 0% |

V6 slog også V5 frozen og simple fixed A/B. Hierarchical transfer skabte værdi, CUPAC reducerede varians, og calibration bestod.

Men safety audit fandt mindst 23/297 = 7,74% falske ACT-episoder, primært efter temporal drift, og harmful individual ACT exposure var 30,40%. Full State gav ingen gevinst over RFM. Verdicts:

- V6 vs BAU economic value: **PASS**;
- what-if calibration: **PASS**;
- cross-merchant transfer: **PASS**;
- decision discovery: **FAIL**;
- safe policy improvement: **FAIL**;
- real merchant evidence: **NONE**.

### E-commerce Decision Layer V6.1

V6.1 tilføjede:

- CANDIDATE, TESTING, ACTIVE, WATCH, SUSPENDED og AVOID lifecycle;
- to uafhængige randomized batches før promotion;
- rolling treatment effect og CUSUM drift monitoring;
- 5% sentinel traffic;
- evidence decay;
- downgrade-only Safety Supervisor;
- Expected Actionable Economic Value discovery;
- RFM som eneste state-repræsentation.

Resultater:

| Metric | V6.1 |
|---|---:|
| Incremental CP vs BAU | +370.625,50 |
| Mean merchant gain | +12.354,18 |
| Paired 95% CI | `[+5.516,07; +20.591,29]` |
| False ACT | 5,08% |
| Unsupported ACT | 0% |
| Harmful ACT exposure | 3,90% |
| Post-reversal ACT | 11 |

V6.1 bevarede økonomisk værdi og reducerede safety failure kraftigt, men bestod ikke `<1%` false-ACT-gaten. False suspension og reactivation var også utilstrækkelige. Verdict: **økonomi PASS, safety FAIL**.

### E-commerce Decision Layer V6.2 — Pack A

V6.2 udvidede lifecycle til:

```text
CANDIDATE
  → TESTING
  → ACTIVE
  → WATCH
  → SUSPENDED
  → REVALIDATING
  → ACTIVE eller AVOID
```

Den tilføjede:

- to-episode ACT leases;
- adaptive sentinel cohorts;
- separate common- og causal-shift diagnostics;
- predictable propensities;
- bounded randomized residual scores;
- variance-adaptive confidence sequences;
- regime-wise global alpha-budget;
- revalidation uden discovery censorship;
- downside budget og BAU fallback.

Den første valgte Pack-A-kandidat gav:

| Metric | Resultat |
|---|---:|
| Incremental CP vs BAU | +500.463,68 |
| Mean merchant gain | +7.819,75 |
| Paired 95% CI | `[+4.952,89; +10.828,10]` |
| Unsupported ACT | 0 |
| Raw false ACT | 2,91% — FAIL |
| Avoidable false ACT | 0,00% — PASS |
| Avoidable upper 95% | 0,789% |
| Harmful exposure | 2,90% — FAIL |
| Post-observable false ACT | 0 |
| Eligible reactivation | 87,5% |

De resterende raw harms skete før en post-change batch kunne være observeret. Det er en reel information-delay-grænse, men det gør ikke raw metric til en PASS.

### V6.2 risk-limiting assurance — seneste status

Den seneste V6.2-iteration tilføjede:

- `LIMITED_ACTIVE`;
- family-specific feedback clocks;
- progressive exposure tiers;
- feedback-delay VaR;
- hybrid risk budgets;
- persistent randomized BAU traffic;
- pathwise drawdown og pre/post-observable harm metrics.

Pack A `risk_hybrid_p10` gav:

| Metric | Resultat |
|---|---:|
| Incremental CP vs BAU | +446.188,46 |
| Paired mean | +6.760,43 |
| Paired 95% CI | `[+4.383,03; +9.365,87]` |
| V6.1 value retained | 86,92% |
| Unsupported ACT | 0 |
| Avoidable false ACT | 0/404 |
| Raw false ACT | 3,22% |
| Post-observable harm CP | 0,00 |
| p99 pathwise drawdown | 1.101,21 |
| Value capture | 44,49% |

En 1.368-cell indistinguishable-world torture suite fandt nul leakage og nul post-observable loss, men maximum pre-observable loss overskred den ønskede tail-grænse.

Fresh development packs E/F/G havde alle positiv incremental CP og positiv CI-lower-bound, men fejlede samlet, fordi:

- action/value capture var for lav;
- p99 drawdown overskred 1.125;
- reactivation generalization var ikke etableret;
- der var for få ACTs til den ønskede error upper-bound.

**Endelig V6.2-status:** development FAIL, ikke freeze-eligible, ingen official final, ingen real-data reveal.

## 19. Anytime inference og risk limiting

V5 implementerede en union-bound Hoeffding confidence sequence. Den eliminerede false promotion i sin null/harmful fixture, men var langsom i profitable worlds.

V6.2 implementerede variance-adaptive sequential inference og validerede den på 6.000 development sequences:

- 4.500 null og 1.500 positive trials;
- continuous peeking;
- adaptive propensities;
- 1–3 episode outcome delay;
- variable stopping;
- common shocks og Student-t noise;
- 0 observerede null false promotions;
- 100% final null coverage;
- minimum positive power 96,4%.

Verdict: **PASS, men konservativ på syntetisk Monte Carlo**. Det beviser ikke validity under real interference, noncompliance, attrition eller fejl i propensity logs.

## 20. Drift, safety lifecycle og information delay

V6 viste, at cumulative positive evidence kan blive stale efter et causal regime shift. V6.1/V6.2 byggede derfor:

- kortvarige ACT leases;
- aktiv sentinel-randomisering;
- WATCH og SUSPENDED states;
- hurtig withholding ved ny negativ batch;
- separat confirmation før AVOID;
- revalidation og reactivation;
- evidence decay;
- common-shock versus treatment-effect-shift separation;
- downside/risk budgets;
- limited exposure før fuld ACTIVE.

V6.2 fjernede continuation efter observerbar skade i Pack A. Den kan dog ikke opdage en treatment-effect reversal, før et nyt treatment outcome er modnet, når pre-decision information er identisk i profitable og harmful worlds. Dette er den vigtigste nuværende informationstekniske begrænsning.

## 21. Data og valideringskilder

Repositoryet indeholder adapters, materialisering eller benchmarks for:

- Hillstrom RCT;
- Criteo uplift;
- X5 RetailHero;
- Open Bandit Pipeline quick sample;
- Dunnhumby Complete Journey;
- H&M;
- JDsearch;
- RetailRocket;
- Online Retail II;
- MT-LIFT adapter/protokol;
- M5 og Dominick's schemas/adapters;
- truth-known continuous retail worlds;
- sequential semi-synthetic merchant fleets.

Korrekte claim boundaries:

- observational data er ikke RCT evidence;
- ukendt assignment provenance er ikke dokumenteret randomization;
- ranking metrics er ikke policy value;
- manglende COGS, shipping, return, discount eller campaign cost betyder, at contribution profit ikke er identificeret;
- synthetic truth evaluerer mekanismer, ikke real merchant transportability.

## 22. Produkt-API og merchant validation

FastAPI-produktfladen ligger i `src/commercial_twin/merchant_validation/api.py` og indeholder routes til:

- data health;
- Shopify/Klaviyo connection contracts;
- single og batch event ingestion;
- customer base;
- customer twin lookup;
- opportunity list/detail;
- experiment create/freeze/assign/read/analyze/results;
- learning ledger.

Der findes også:

- merchant validation contracts;
- service orchestration;
- connector interfaces;
- learning matcher;
- database schema og migrations;
- onboarding- og data contract-dokumentation.

Disse interfaces er produktformede, men rigtige credentials, drift, merchant-data og prospective experiments mangler før en commercial claim.

## 23. Research dashboard og frontend

### Research dashboard

Streamlit research cockpit kan vise forecasting, causal estimation, uncertainty, support, economics, calibration og benchmarkdiagnostics. Syntetiske views skal være mærket:

> SYNTHETIC — NOT COMMERCIAL EVIDENCE

### Next.js-produkt

Der er bygget en Next.js 16.1.6 / React 19.2.4 præsentationsskal med routes til:

- `/`;
- `/onboarding`;
- `/data-health`;
- `/customer-base`;
- `/opportunities`;
- `/opportunities/[id]`;
- `/experiments`;
- `/experiments/new`;
- `/experiments/[id]/results`;
- `/ledger`;
- `/settings/connections`.

Forsiden viser Exergi Decision Feed. De seneste UI-rettelser:

- fjernede de tomme firkantikoner i venstremenuen;
- gjorde shell/dashboard-linjen mørkere og mere synlig;
- gjorde sidebar-divideren mørkere.

Frontendens merchant-sider er fortsat eksempel-/demodata og er ikke dokumentation for en live backend-integration eller real commercial evidence.

## 24. Lokal udvikling og Vercel

`package.json` indeholder:

```bash
npm run dev
npm run build
npm run start
```

Den oprindelige `npm run dev`-fejl skyldtes manglende `package.json` i repository-roden. Next.js-projektet og nødvendige configs blev derefter oprettet.

Vercel-builden blev senere repareret med root-level `vercel.json`:

```json
{
  "$schema": "https://openapi.vercel.sh/vercel.json",
  "framework": "nextjs",
  "buildCommand": "npm run build",
  "outputDirectory": null
}
```

Det tvinger Next.js framework preset og nulstiller en potentiel forkert static `public` output override. Rettelsen og UI-ændringerne blev committed som `cbf895e` og pushet til `origin/main`, hvilket udløste en ny Vercel-deployment.

Den lokale production build består. Den eksterne Vercel-deployments endelige status skal fortsat aflæses i Vercel-dashboardet.

## 25. Aktuel test- og buildstatus

Kørt igen 27. august 2026:

| Check | Resultat |
|---|---|
| `.venv/bin/pytest -q` | PASS — 284 tests |
| `.venv/bin/ruff check .` | PASS — All checks passed |
| `.venv/bin/mypy src` | PASS — 143 source files |
| `npm run build` | PASS |
| Next.js routes | 11 genereret |
| `git diff --check` før seneste deploycommit | PASS |

Testdækning inkluderer blandt andet:

- leakage og temporal splitting;
- cross-fitting;
- deterministic seeds;
- treatment density og clipping;
- support og unsupported ACT;
- bootstrap og interval ordering;
- oracle isolation;
- experiment assignment og propensities;
- Merchant Learning;
- model selection og freeze;
- economics og regret;
- Prediction Ledger;
- opportunity discovery;
- safe policy;
- V5, V6, V6.1 og V6.2 components.

## 26. Centrale filer og mapper

### Scientific core

- `src/decision_engine/causal/`
- `src/decision_engine/decision/`
- `src/decision_engine/economics/`
- `src/decision_engine/forecasting/`
- `src/decision_engine/uncertainty/`
- `src/decision_engine/robustness/`
- `src/decision_engine/ledger/`
- `src/decision_engine/registry/`
- `src/decision_engine/benchmark/`

### Commercial Twin

- `src/commercial_twin/customer_twin_core.py`
- `src/commercial_twin/dynamic_customer_state.py`
- `src/commercial_twin/world_state.py`
- `src/commercial_twin/ecommerce_opportunities.py`
- `src/commercial_twin/safe_policy.py`
- `src/commercial_twin/progressive_decision.py`
- `src/commercial_twin/merchant_validation/`
- `src/commercial_twin/prediction_v2/`

### Benchmarks

- `benchmarks/customer_twin_decision_lab_v1/`
- `benchmarks/customer_twin_decision_lab_v2/`
- `benchmarks/customer_twin_research_v1/`
- `benchmarks/ecommerce_decision_layer_v3/`
- `benchmarks/ecommerce_decision_layer_v4/`
- `benchmarks/ecommerce_decision_layer_v5/`
- `benchmarks/ecommerce_decision_layer_v6/`
- `benchmarks/ecommerce_decision_layer_v6_1/`
- `benchmarks/ecommerce_decision_layer_v6_2/`
- `benchmarks/hm_day1_v2/`
- `benchmarks/jdsearch_behavioral/`
- `benchmarks/jdsearch_dynamics/`

### Product surfaces

- `src/commercial_twin/merchant_validation/api.py`
- `apps/research_dashboard.py`
- `app/`
- `home.tsx`
- `package.json`
- `vercel.json`

### Samlet dokumentation

- `PROJECT_STATUS.md`
- `ALT_BYGGET_VERIFIED_CUSTOMER_TWIN_OG_DECISION_LAYER.md`
- `docs/HELE_PRODUKTET_VERIFIED_CUSTOMER_TWIN.md`
- `docs/continuous_dr_v4_report.md`
- `docs/support_gate_v5_report.md`
- `docs/ALT_BYGGET_MODELSELEKTION_OG_OKONOMISK_POLICY.md`
- `benchmarks/ecommerce_decision_layer_v5/FINAL_REPORT.md`
- `benchmarks/ecommerce_decision_layer_v6/FINAL_REPORT.md`
- `benchmarks/ecommerce_decision_layer_v6_1/FINAL_REPORT.md`
- `benchmarks/ecommerce_decision_layer_v6_2/RISK_LIMITING_ASSURANCE_REPORT.md`

## 27. Capability matrix

| Capability | Aktuel verdict |
|---|---|
| Typed scientific architecture | PASS |
| Leakage safety og frozen evaluation | PASS |
| Prediction ranking | PARTIAL |
| Probability/population calibration | PARTIAL/FAIL afhængigt af dataset |
| Deterministisk opportunity discovery | PASS på planted fixture |
| Discovery rank-one i komplekse worlds | FAIL/PARTIAL |
| Merchant Memory påvirker næste decision | PASS |
| Randomized causal plumbing | PASS synthetic / PARTIAL public data |
| Continuous observational dose-response | IKKE KOMMERCIELT VALIDERET |
| Conditional support/refusal | PASS som mekanisme |
| Contribution-profit optimization | PASS som mekanisme |
| Profit versus revenue objective | PASS synthetic |
| Model tournament og freeze | PASS som proces |
| V6 synthetic value versus BAU | PASS |
| V6 what-if calibration | PASS synthetic |
| Cross-merchant hierarchical value | PASS synthetic V6 |
| Full State versus RFM | INGEN DOKUMENTERET GEVINST |
| Safe policy improvement | FAIL |
| V6.2 post-observable containment | PASS på Pack A |
| V6.2 multi-pack robustness | FAIL |
| Real merchant causal evidence | NONE |
| Real merchant profit evidence | NONE |
| Autonomous production readiness | NO |

## 28. Hvad produktet ærligt kan sige nu

Produktet kan sige:

- “Vi har fundet et statistisk og økonomisk materielt problem i denne population.”
- “Dette er predictive/descriptive evidence, ikke automatisk causal evidence.”
- “Tidligere randomiseret evidence er high support, partial, stale eller out of support.”
- “Denne action har/har ikke support i den aktuelle state.”
- “Policy value slår/slår ikke BAU på held-out evidence.”
- “Heterogeneity er/er ikke demonstreret.”
- “Vi anbefaler TEST, VERIFY, AVOID eller BAU, fordi ACT-gaten ikke er bestået.”
- “Contribution profit kan ikke beregnes troværdigt uden nødvendige cost fields.”
- “På en frossen syntetisk V6-fleet skabte systemet positiv værdi mod BAU.”
- “V6.2 stoppede før final, fordi robustness/safety gates fejlede.”

## 29. Hvad produktet ikke må påstå

Produktet må ikke sige:

- “Exergi er production ready.”
- “Exergi har bevist real merchant profit.”
- “Full Customer State er bedre end RFM.”
- “Personaliseret targeting er generelt valideret.”
- “Observational commerce data beviser causal effects uden antagelser.”
- “Hidden confounding er løst.”
- “Et højt AUUC/Qini beviser økonomisk policy value.”
- “V6.2 bestod final.”
- “Ingen harmful ACT kan forekomme ved delayed outcomes.”
- “Den øverst rangerede opportunity er altid den bedste.”
- “Frontendens eksempeldata er live commercial evidence.”

## 30. Største resterende fejl

Den største resterende fejl er nu todelt:

1. **Information delay og safety:** En treatment effect kan ændre sig efter sidste observerede positive batch. Uden et tidligere policy-visible signal kan systemet først opdage dette, når nye outcomes modner. V6.2 begrænser post-observable skade, men raw harm og tail drawdown er stadig over de frosne mål.
2. **Generaliserbar decision discovery:** Systemet kan ofte finde en relevant top-tre-liste, men rank-one action value og anti-cowardice/value capture generaliserer ikke stabilt over nye packs.

Full State har desuden endnu ikke slået RFM, og real-merchant transportability er helt ubevist.

## 31. Hvad der skal til før næste evidensniveau

Før real-merchant execution bør følgende være opfyldt:

- en ny preregistreret version skal bestå flere development packs uden efterfølgende tuning;
- p99 pathwise drawdown skal holdes under en eksplicit grænse;
- action/value capture skal være tilstrækkelig til, at sikkerhed ikke blot opnås gennem inaktivitet;
- reactivation skal være demonstreret på uafhængige worlds;
- discovery skal forbedres uden eksplosiv low-value testing;
- propensity logging, outcome delays og cost semantics skal være robuste;
- real merchant evaluation skal begynde read-only/shadow-mode;
- prospective randomized evidence skal etableres før autonom ACT.

Det næste arbejde bør være videnskabelig validering af denne kerne, ikke flere features, connectors, frontend-sider eller ny produktscope.

## 32. Endelig vurdering

Exergi har bevæget sig fra en bred Customer Twin-idé til en langt mere disciplineret beslutningsmekanisme:

```text
State
→ Opportunity
→ Action
→ Randomized evidence
→ Economic response
→ Memory
→ Reversible næste beslutning
```

De vigtigste dokumenterede fremskridt er:

1. leakage-sikre state- og evalueringskontrakter;
2. causal/economic separation;
3. support-aware refusal;
4. modeltournaments frem for en fast DR-default;
5. Merchant Learning, som reelt ændrer næste beslutning;
6. contribution-profit frem for revenue-only optimization;
7. anytime-valid og value-of-information-baseret testing;
8. V6 positiv syntetisk værdi mod kompetent BAU;
9. V6.1/V6.2 stærkt reduceret drift- og false-ACT-skade;
10. fail-closed freeze, når development gates ikke består;
11. en kompilerbar Next.js-produktvisning og Vercel-deploymentkonfiguration.

Den afgørende konklusion er fortsat:

> Exergi har bevist, at den videnskabelige beslutningsmekanisme kan skabe positiv contribution-profit-værdi i en frossen truth-known syntetisk benchmark og kan nægte unsupported ACT. Exergi har ikke endnu bevist, at mekanismen er sikker og robust nok på tværs af nye verdener eller skaber real merchant profit.

**Nuværende valideringsniveau:** Level 1 — synthetic economic validity.  
**Ready for real-merchant autonomous decisions:** Nej.  
**Ready for en ny, preregistreret scientific iteration:** Ja.
