# Verified Customer Twin — samlet produktbeskrivelse

**Statusdato:** 26. august 2026  
**Repository:** `/Users/madsflyvholm/Desktop/decision layer`  
**Aktuel samlet videnskabelig konklusion:** **CUSTOMER TWIN TECHNICAL THESIS: NO**  
**Softwarestatus:** Et omfattende, testet research- og beslutningssystem med flere fungerende delkomponenter, men uden tilstrækkelig evidens til at kalde den samlede Customer Twin videnskabeligt valideret eller produktionsklar.

## 1. Produktets formål

Verified Customer Twin er en videnskabelig beslutningsmotor, som skal kunne repræsentere kundeadfærd, forudsige fremtidige udfald, simulere naturlige kundedynamikker, estimere effekten af merchant-handlinger og vurdere, hvilken handling der skaber størst forventet økonomisk værdi.

Den langsigtede produktkæde er:

```text
Observeret kundehistorik
        ↓
Customer State
        ↓
Fremtidig adfærdsfordeling
        ↓
Merchant Action + kausal respons
        ↓
Kontrafaktisk transition
        ↓
Policy value og økonomisk beslutning
```

Produktets vigtigste videnskabelige regel er:

```text
Prediction ≠ causal effect ≠ policy value ≠ contribution profit
```

En model, som kan forudsige køb, har ikke dermed bevist, at den kan estimere effekten af en rabat, e-mail eller kampagne. En estimeret effekt er heller ikke automatisk en profitabel policy. Derfor holdes prediction, causal inference, uncertainty, support, economics og decision policy adskilt i både kode og rapportering.

## 2. Produktets hovedlag

### 2.1 Decision Engine

`decision_engine` indeholder de generiske videnskabelige byggesten:

- leak-safe forecasting og kronologiske benchmark-splits;
- diskrete og kontinuerlige kausale estimatorer;
- uncertainty, calibration og probabilistiske metrics;
- conditional support og overlap-diagnostik;
- økonomiske profit- og utility-transformationer;
- beslutningspolicy med `ACT`, `EXPERIMENT` og `ABSTAIN`;
- drift, placebo, sensitivity og øvrig falsifikation;
- append-only Prediction Ledger og model-performance registry.

Dette lag er domæneuafhængigt. Det producerer estimater og evidens, men ejer ikke kundestate eller commerce-specifikke handlinger.

### 2.2 Commercial Twin

`commercial_twin` er produktlaget oven på Decision Engine. Det indeholder:

- immutable customer-, company- og world-state-kontrakter;
- Customer Twin-factory og orchestration;
- adfærdsmodelprotokoller;
- dynamisk kundestate og populationsmodeller;
- cohorts, readiness og evidence safety;
- H&M-, JDsearch-, Online Retail II-, RetailRocket- og Complete Journey-workflows;
- query-routing og produktformede svar;
- state snapshots, simulation results og outcome updates.

### 2.3 Commerce-domænet

`domains.commerce` oversætter den generiske motor til commerce:

- typed actions;
- continuous-discount behavior adapter;
- syntetiske fixtures;
- real-data runner;
- world-state ablation;
- commerce-specifik økonomi og constraints.

Den eneste fuldt gennemførte action-adapter er continuous discount. Prisændring, free shipping og generel promotion er typed interfaces, men ikke videnskabeligt validerede adfærdsmodeller.

## 3. State-modellen

### CustomerState

Customer State beskriver den observerbare kundesituation ved et bestemt cutoff. Den kan indeholde:

- recency, frequency og monetary value;
- købshistorik og produkt-/kategori-affinitet;
- views, clicks, carts og nyere intent;
- lifecycle- og behavioral cohort;
- promotion response, retention og engagement;
- dynamisk latent state, hvor benchmarken understøtter det.

State bygges point-in-time og må ikke indeholde fremtidige events, outcome-labels eller post-treatment information. Rå PII er ikke en del af state-kontrakten.

### CompanyState

Company State beskriver merchantens observerede interne situation:

- produkter og kategorier;
- priser, discounts og offers;
- cost- og marginfelter, når de findes;
- kampagner og kanaler;
- inventory og fulfillment;
- andre tidsstemplet interne forhold.

### WorldState

World State indeholder eksterne, tidsstemplet signaler med provenance, geography, confidence og vintage-sikkerhed. Der er implementeret nationale og amerikanske state/regional-signaler samt geografisk vægtning af customer exposure.

World State-resultaterne er **MIXED**. CPI forbedrede point error beskedent i Dominick's-ablationen, men forværrede bias, interval width og WIS. Dette er prediction-evidens, ikke dokumentation for kausal effekt.

### CommercialState

`CommercialState` er det immutable snapshot af Customer State, Company State og World State, som bruges i én simulation. Snapshot-hash, modelversioner, antagelser, support og uncertainty kan gemmes sammen med predictionen.

## 4. Prediction Engine

Prediction-laget er designet til at efterligne en rigtig beslutningsdag:

- event time, observation time, decision time og action time er eksplicitte;
- historikken fryses ved cutoff;
- expanding-window og rolling-origin splits bruges i stedet for tilfældige tidsserie-splits;
- lag- og rolling-features er strengt shiftede;
- predictions skrives til ledger før final-targets må afsløres;
- quick mode har kun pipeline-authority og må ikke vælge officiel vinder eller afsløre finalen;
- development tournament vælger konfigurationen;
- konfigurationen fryses før én officiel final reveal.

Implementerede forecast-komponenter omfatter sæsonbaselines, LightGBM, kvantilmodeller, ensemblevægtning, split-conformal calibration og metrics som MAE, RMSE, WAPE, MASE, pinball loss, coverage, interval width, WIS og empirisk CRPS.

## 5. Customer behavior og predictive state

### H&M Day-1

H&M V2 målte, om et nyt systems første customer snapshot kunne forudsige senere køb på en låst 70/15/15 customer split.

- Purchase-history-only final AUROC: cirka **0,7414**.
- Purchase prediction har reel ranking information.
- Kalibrering fejlede.
- Aggregate buyer forecast fejlede.

Resultatet understøtter købsprediktion, men ikke en komplet Customer Twin.

### JDsearch Behavioral

JDsearch testede, om behavioral events giver information ud over purchases:

- purchase-only AUROC: **0,7502**;
- full-behavior AUROC: **0,7992**;
- forbedring: **+0,0490**.

Clicks, carts og recent intent skabte materiel ekstra predictive information. Behavioral Information-laget har derfor status **PASS**.

### JDsearch Dynamics

JDsearch Dynamics byggede kundestate og sekvensmodeller til one-step og multi-step event dynamics.

- predictive state: **PASS**;
- one-step dynamics: **PASS**;
- multi-step event dynamics: **PASS**;
- state compression: **FAIL**;
- population rollout: **FAIL**;
- K=20 calibration: **FAIL**.

Den officielle final er allerede afsløret én gang og må ikke genbruges til ny tuning.

## 6. Calendar-time dynamics og population simulation

### RetailRocket

RetailRocket blev anvendt til faktisk continuous-time adfærd med Unix timestamps.

- Dataperiode: **3. maj 2015 til 18. september 2015 UTC**.
- Valgt implementeret model: conditional exponential/Poisson hazard med GBDT direct heads.
- TPP NLL: **1,796**.
- Time-rescaling KS: **0,091**.
- 7-dages buyer population error: **27,9 %**.
- 30-dages buyer population error: **22,4 %**.
- Predictive sufficiency blev ikke demonstreret.
- Population predictive-interval coverage var nul.

Continuous-time state er derfor **PARTIALLY**, mens population simulation er **FAIL**.

### Dunnhumby Complete Journey

Complete Journey blev brugt som long-horizon retail replication:

- 30-dages buyer error: **8,46 %**;
- 90-dages buyer error: **4,88 %**;
- 30-dages ECE: **0,0849**;
- 90-dages ECE: **0,0478**.

Aggregate accuracy var bedre end RetailRocket, men de frosne calibration-gates blev ikke bestået. Den officielle final er afsløret præcis én gang.

### Customer Population Engine V1–V3

Der er bygget tre generationer af population engine:

- **V1 — FAIL:** væsentlig population-labeling omission og generativ inkohærens gav for høj revenue.
- **V2 — MIXED:** separat purchase incidence, conditional order count, conditional order value, new-customer arrivals og top-down challenger forbedrede arkitekturen.
- **V3 — videnskabeligt FAIL:** reconciliation mellem bottom-up heterogenitet og top-down totals blev bygget, men første final reveal indeholdt en implementation invariant-fejl. Holdoutet er derfor burned. Den korrigerede kørsel er kun diagnostisk og kan ikke opgraderes til officiel PASS.

## 7. Causal action response

### Diskrete actions

Systemet indeholder naive estimators, outcome regression, S-learner, T-learner, X-learner, R-/DR-varianter og valgfri EconML-integration. Modelvalg foretages development-only pr. decision type; DR er en challenger og ikke en antaget default.

Der anvendes blandt andet:

- cross-fitting;
- propensity og overlap-diagnostik;
- standardized balance;
- effective sample size;
- AIPW/doubly robust scores;
- estimator sign/rank agreement;
- placebo og sensitivity;
- held-out policy-value evaluation.

Post-treatment mediators må ikke anvendes som baseline covariates.

### Hillstrom

Hillstrom er et randomiseret multi-arm e-mail-benchmark.

- Men's email conversion ATE: **0,00610**, interval ekskluderer nul.
- Women's email conversion ATE: **0,00348**, interval inkluderer nul.
- Learned policy matchede den bedste statiske Men's-email policy.
- Learned targeting dokumenterede ikke ekstra værdi over bedste statiske action.

Status: **PARTIALLY**. Randomiseret treatment effect er demonstreret, men personaliseret heterogen policy value er ikke.

### Criteo Uplift

Criteo-resultaterne viser reel eksperimentel treatment signal, men ingen gevinst fra selektiv targeting over global behandling:

- development-vinder: S-learner;
- selective policy value: **0,003033**;
- treat-all value: **0,003074**.

Den kundevendte `DO THIS`-gate er derfor fail-closed. Interne `TEST THIS` og `NOT ENOUGH EVIDENCE` kan stadig bruges.

### MT-LIFT

MT-LIFT var den planlagte primære nye multi-action validering, men publisher-filen kunne ikke hentes uden autoriseret Google Drive-adgang. Der blev ikke oprettet kunstig mirror-data, ikke trænet modeller og ikke afsløret en officiel final.

Status: **UNPROVEN**.

### Synthetic Layer 3

På 100 truth-known syntetiske seeds bestod den adjusted estimator de preregistrerede recovery- og coverage-gates:

- adjusted bias: **-0,0000066**;
- adjusted RMSE: **0,005796**;
- mean absolute segment error: **0,007189**;
- 95 % interval coverage: **0,93**;
- placebo false-positive rate: **0,04**.

Dette validerer matematikken under den kendte DGP, men ikke causal identification hos en rigtig merchant.

## 8. Continuous discount og økonomisk optimering

Systemets continuous-treatment lag estimerer en dosisrespons:

```text
μ(d) = E[Y(d)],    d ∈ [0, 0.30]
```

Den nye `ContinuousDRDoseResponseEstimator` anvender strengt kronologisk cross-fittede nuisance-modeller for:

- outcome regression `m(d, x) = E[Y | D=d, X=x]`;
- conditional treatment density `f(d | x)`;
- en lokal kernel-baseret doubly robust korrektion.

Treatment density er en aktiv del af estimatoren og rapporterer density clipping, effektive densiteter, extreme weights og ESS. Synthetic oracle truth er fysisk adskilt og bruges kun efter predictions er frosset.

### ConditionalSupportGate

Support afgøres kontekstspecifikt ud fra:

- conditional treatment density;
- local effective sample size;
- nærmeste observerede dose;
- kernel-weighted support;
- overlap med træningspopulationen;
- extrapolation distance;
- model disagreement og instability.

Et ukonstraint optimum uden support kan aldrig returnere `ACT`.

### Counterfactual uncertainty

Blocked/clustered bootstrap genkører dataresampling, nuisance fitting, density fitting, DR-estimation og economic transformation. Intervaller rapporteres med point estimate, lower/upper bound, bootstrap standard error og antal gyldige replicates. Calibration vurderes mod synthetic truth efter prediction freeze.

### Economic layer

Estimatoren producerer en response distribution. Et separat økonomilag omdanner den til contribution profit, hvorefter optimizeren anvender support-, margin-, business- og risk-constraints.

Hvis profitfladen er flad, returneres et robust near-optimal interval frem for falsk decimalpræcision. Hvis nødvendige cost-data mangler, returneres `ECONOMICS_NOT_IDENTIFIED` eller `NOT_COMPUTABLE_MISSING_COST_FIELDS`.

### Aktuel status

Continuous DR-infrastrukturen, support invarianten, bootstrap og beslutningskontrakter er implementeret. Den samlede continuous-retail videnskabelige kapabilitet er dog ikke godkendt:

- causal dose-response: **FAIL/MIXED afhængigt af regime**;
- calibration: **FAIL**;
- support/abstention: forbedret teknisk, men ikke tilstrækkeligt dokumenteret som generel real-data-kapabilitet;
- hidden confounding: ikke løst og rapporteres separat;
- real merchant discount response: **UNPROVEN**.

## 9. Model selection og beslutningspolicy

Commercial Twin antager ikke længere, at én bestemt model altid er bedst. For hver decision type:

1. alle gyldige challengers køres på development-data;
2. ranking, calibration og policy value sammenlignes;
3. vinderen fryses før final test;
4. final targets åbnes én gang;
5. resultatet gemmes i registry og Prediction Ledger.

Kundevendt `DO THIS` kræver, at den gated policy slår:

- ungated policy;
- simple targeting;
- treat-all;
- treat-none;
- relevante cost- eller capacity-constrained baselines.

Dette krav blev ikke opfyldt på Criteo eller Hillstrom. Kundevendt action gating er derfor deaktiveret for disse kapabiliteter. Internt kan systemet stadig anbefale et eksperiment eller konkludere, at evidensen er utilstrækkelig.

## 10. ACT, EXPERIMENT og ABSTAIN

### ACT

Kræver samtidig:

- understøttet action;
- acceptabel uncertainty;
- ingen hard falsification failure;
- tilstrækkelig modelstabilitet;
- acceptabel sensitivity;
- meningsfuld økonomisk fordel;
- empirisk valideret gate for den konkrete decision type.

### EXPERIMENT

Bruges når en action ser lovende ud, men evidensen ikke kan skelne sikkert mellem kandidater. Systemet kan foreslå to behandlinger og beregne omtrentlig sample size/power.

### ABSTAIN

Bruges ved manglende support, alvorlig identifikationsfejl, dårlig datakvalitet eller så stor instability, at selv en eksperimentanbefaling ikke kan forsvares.

Produktets centrale safety invariant er:

```text
Unsupported action → ACT = 0 tilladte tilfælde
```

## 11. Off-policy evaluation

OPE-laget implementerer IPS, SNIPS, doubly robust estimation, supportkontrol og effective sample size.

På Open Bandit quick-data:

- DR-estimat: **0,005043**;
- empirisk BTS target value: **0,004200**;
- ESS: **2.638,87 / 10.000**;
- maksimal importance weight: **9,62**;
- unsupported fraction: **0,3 %**.

Dette validerer kun estimator-plumbing. Den officielle 26M-rækkers protokol og præcise context-specific target propensities er ikke kørt. Der findes derfor ingen officiel freeze/reveal, og Off-Policy Decision Value er **UNPROVEN**.

## 12. Longitudinel kontrafaktisk simulation

Der er implementeret et syntetisk sequential SCM-program med randomized, static-confounding, time-varying-confounding, treatment-affected-confounding og weak-overlap scenarier.

- G-computation bestod komponenttestene med policy-effect error under **0,031**.
- MSM-implementeringen var upræcis.
- Sequential DR er ikke implementeret.
- Real repeated merchant interventions findes ikke i de offentlige data.

Samlet status:

- synthetic implementation: **FAIL** som komplet lag;
- real-world longitudinal counterfactual: **UNPROVEN**;
- krav: **REAL MERCHANT RANDOMIZED LONGITUDINAL DATA REQUIRED**.

## 13. Prediction Ledger og registry

Prediction Ledger er append-only og kan gemme:

- prediction/simulation før outcome reveal;
- cutoff, state hash og config hash;
- model- og data-version;
- support, uncertainty og assumptions;
- frozen prediction manifests;
- efterfølgende outcomes og evaluation records.

ModelPerformanceRegistry gemmer decision-specifik performance og valgte defaults. `CommercialTwin.update(...)` forbinder observerede outcomes med tidligere snapshots og opretter calibration- og decision-performance records.

Den tilsigtede learning loop er:

```text
snapshot → simulate → decide → observe → calibrate → evaluate
```

## 14. Query-, evidence- og readiness-lag

Twin Query Engine omsætter spørgsmål til den korrekte videnskabelige kapabilitet. Evidence safety forhindrer blandt andet:

- kausalt sprog fra rene predictions;
- profitpåstande uden økonomiske inputs;
- discount-response fra data uden identificerbar discount assignment;
- world-state correlation præsenteret som kausal effekt;
- syntetiske resultater præsenteret som commercial evidence.

Readiness er dekomponeret pr. kapabilitet. Produktet returnerer ikke én kunstig samlet confidence score.

## 15. Data og provenance

Repositoryet indeholder eller har behandlet følgende evidenskilder:

| Datasæt | Primær rolle | Evidensstatus |
|---|---|---|
| H&M | Day-1 purchase prediction | Prediction ranking støttet; calibration/population fejlede |
| JDsearch | Behavioral value og dynamics | Behavioral PASS; dynamic PARTIALLY |
| Online Retail II | Customer State og population | Real-data state støttet; population samlet ikke bestået |
| Dunnhumby Complete Journey | Long-horizon population og causal backtest | Population calibration fejlede; causal backtest insufficient |
| RetailRocket | Calendar-time dynamics | Continuous-time PARTIALLY; population FAIL |
| Hillstrom | Randomiseret multi-arm e-mail | Treatment effect støttet; personalisering ikke støttet |
| Criteo Uplift | Randomiseret uplift replication | Real response signal; selective policy slog ikke treat-all |
| MT-LIFT | Planlagt multi-action causal benchmark | UNPROVEN — publisher access blocked |
| Open Bandit | Logged-action OPE | Quick plumbing only; officiel værdi UNPROVEN |
| Synthetic retail/SCM | Truth-known metodetest | Flere komponenter består; kan ikke generaliseres til merchants |

Alle officielle artifacts har provenance, hashes, seeds og freeze/reveal-semantik, hvor workflowet er gennemført. Authenticated eller licensbeskyttede kilder omgås ikke.

## 16. Research dashboard og frontend

### Research dashboard

Streamlit-cockpittet kan vise:

- data health og cutoffs;
- forecasting og probabilistic calibration;
- causal diagnostics og falsifikation;
- continuous dose-response og uncertainty;
- supportregioner og economic range;
- `ACT` / `EXPERIMENT` / `ABSTAIN`;
- ledger-status og benchmarkresultater.

Syntetiske visninger er mærket:

```text
SYNTHETIC — NOT COMMERCIAL EVIDENCE
```

Kør med:

```bash
uv run streamlit run apps/research_dashboard.py
```

### Next.js-visningsskal

Repositoryet indeholder også en separat Next.js home-visning med `package.json`, `app/page.tsx`, `app/layout.tsx`, styling og `home.tsx`. Den kan startes med:

```bash
npm run dev
```

Denne frontend er en visningsskal. Den ændrer ikke den videnskabelige evidensstatus og er ikke en Shopify-integration eller et autonomt commerce-produkt.

## 17. Automatiserede tests og kvalitet

Seneste fulde lokale verifikation:

| Kontrol | Resultat |
|---|---|
| `.venv/bin/pytest -q` | **PASS — 218 tests** |
| `.venv/bin/ruff check .` | **PASS** |
| `.venv/bin/mypy src` | **PASS — 124 source files** |

Testpakken dækker blandt andet:

- timestamp- og leakage-invarianter;
- quick/development/final authority;
- final reveal guards;
- forecasting og calibration;
- cross-fitting og causal recovery;
- treatment density og support;
- bootstrap uncertainty;
- economics og robust range;
- `ACT`, `EXPERIMENT` og `ABSTAIN`;
- oracle isolation;
- ledger og registry;
- population aggregation;
- OPE toy-identiteter;
- query routing og evidence safety.

Repositorymappen er ikke initialiseret som et Git-repository, så der findes ingen commit-historik eller Git-status at rapportere.

## 18. Produktets aktuelle capability matrix

| Kapabilitet | Status | Hvad evidensen siger |
|---|---|---|
| Typed decision contracts | PASS | Implementeret og testet |
| Leak-safe benchmark authority | PASS | Quick kan ikke reveal; freeze/reveal guards findes |
| Behavioral information | PASS | JDsearch full behavior gav +0,049 AUROC |
| Purchase prediction | PARTIALLY | Ranking virker; calibration og aggregates fejlede |
| Dynamic predictive state | PARTIALLY | One-/multi-step virker; compression/calibration fejlede |
| Calendar-time state | PARTIALLY | RetailRocket time model virker, sufficiency ikke bevist |
| Stable population simulation | FAIL | RetailRocket og population-programmet består ikke gates |
| Synthetic causal recovery | PASS som komponent | Truth-known recovery og coverage bestod |
| Randomized action response | PARTIALLY | Hillstrom/Criteo signal; primær MT-LIFT validering mangler |
| Personalized targeting value | FAIL/UNPROVEN | Slog ikke simple globale policies |
| Continuous discount causal response | FAIL/UNPROVEN real-world | Infrastruktur findes; real merchant identification mangler |
| Conditional unsupported-action refusal | PASS som software-invariant | Unsupported optimum kan ikke ACT |
| Off-policy decision value | UNPROVEN | Kun Open Bandit quick plumbing kørt |
| Longitudinal counterfactual | FAIL synthetic / UNPROVEN real-world | G-comp virker; MSM/Sequential DR ufuldstændig |
| Contribution-profit policy | UNPROVEN | Public data mangler komplette costfelter |
| World State | MIXED | Beskeden predictive gevinst, ingen kausal proof |
| Customer-facing `DO THIS` | DISABLED for ikke-validerede decisions | Gate slog ikke simple alternativer |

## 19. Hvad produktet kan bruges til nu

Forsvarligt understøttet anvendelse:

- bygge leak-safe, point-in-time customer snapshots;
- udføre reproducerbare prediction- og causal research-benchmarks;
- måle behavioral information value;
- sammenligne causal/uplift-modeller på development-data;
- fryse modelvalg før final evaluation;
- diagnosticere calibration, overlap, support og instability;
- afvise unsupported actions;
- foreslå kontrollerede eksperimenter ved utilstrækkelig evidens;
- registrere predictions, outcomes og modelperformance append-only;
- demonstrere produktflowet på tydeligt mærkede syntetiske fixtures.

## 20. Hvad produktet ikke må påstå endnu

Produktet må ikke hævde, at det kan:

- simulere en stabil fremtidig kundepopulation generelt;
- bevise predictive state sufficiency;
- estimere kausal rabatrespons fra vilkårlige observationsdata;
- løse hidden confounding;
- dokumentere værdien af personaliseret targeting over simple policies;
- evaluere arbitrary policies uden support og kendte propensities;
- simulere langvarige sekvenser af merchant-actions på rigtige kunder;
- beregne contribution profit uden COGS, returns, shipping og campaign costs;
- agere autonomt eller eksekvere kampagner;
- kaldes production ready.

## 21. Data der kræves fra den første merchant

En rigtig validering kræver som minimum:

- stabil pseudonym customer identity;
- timestampede web-, search-, click-, cart- og checkout-events;
- orders, line items, quantity, gross price og discount;
- campaign ID, treatment/control assignment og assignment probability;
- eligibility, assignment time og exposure time;
- returns, refunds og cancellations;
- COGS, shipping subsidy, campaign cost og payment costs;
- 12–24+ måneders historik;
- mindst cirka 50.000 kunder og 10.000 orders per måned;
- gentagne randomiserede kommercielle eksperimenter.

Det vigtigste manglende bevis er longitudinal randomized merchant data med faktiske økonomiske outcomes.

## 22. Centrale artifact paths

- Master scientific verdict: `benchmarks/customer_twin_research_v1/MASTER_REPORT.md`
- Claim matrix: `benchmarks/customer_twin_research_v1/claim_matrix.json`
- Merchant data requirements: `benchmarks/customer_twin_research_v1/REAL_MERCHANT_DATA_REQUIREMENTS.md`
- H&M V2: `benchmarks/hm_day1_v2/`
- JDsearch Behavioral: `benchmarks/jdsearch_behavioral/`
- JDsearch Dynamics: `benchmarks/jdsearch_dynamics/`
- RetailRocket: `benchmarks/customer_twin_research_v1/retailrocket/`
- Dunnhumby: `benchmarks/customer_twin_research_v1/dunnhumby/`
- Criteo replication: `benchmarks/customer_twin_research_v1/criteo_replication/`
- Hillstrom sanity: `benchmarks/customer_twin_research_v1/hillstrom_sanity/`
- Open Bandit: `benchmarks/customer_twin_research_v1/open_bandit/`
- Sequential synthetic SCM: `benchmarks/customer_twin_research_v1/sequential_causal_synthetic/`
- Continuous DR report: `docs/continuous_dr_v4_report.md`
- Model-selection report: `docs/model_selection_and_economic_policy_validation.md`
- Customer Twin Core V1: `docs/ALT_BYGGET_CUSTOMER_TWIN_CORE_V1.md`
- Population V1–V3 reports: `docs/CUSTOMER_POPULATION_ENGINE_V1_REPORT.md`, `docs/CUSTOMER_POPULATION_ENGINE_V2_REPORT.md`, `docs/CUSTOMER_POPULATION_ENGINE_V3_REPORT.md`

## 23. Endelig produktvurdering

Verified Customer Twin er ikke et tomt koncept. Repositoryet indeholder reelle state-kontrakter, leak-safe predictions, model tournaments, continuous DR, support gating, uncertainty, economics interfaces, causal benchmarks, OPE-matematik, population engines, Prediction Ledger, registry og produktformet orchestration.

Det stærkeste dokumenterede resultat er, at systemet kan opbygge og evaluere flere nødvendige komponenter separat og nægte at konvertere utilstrækkelig evidens til en unsupported handling.

Den samlede kæde er imidlertid ikke bevist. Population simulation fejler, personalized policy value har ikke slået simple alternativer, primær multi-action og fuld OPE-validering mangler, og longitudinal causal simulation er ufuldstændig.

Derfor er den korrekte samlede vurdering:

```text
CUSTOMER TWIN TECHNICAL THESIS: NO
```

Det næste videnskabeligt nødvendige skridt er ikke mere produktbredde. Det er en prospektiv merchant-validering med point-in-time data, gentagne randomiserede handlinger, kendte propensities og komplette økonomiske outcomes.
