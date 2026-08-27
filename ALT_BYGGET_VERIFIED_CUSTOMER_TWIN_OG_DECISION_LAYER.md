# Alt bygget — Verified Customer Twin og E-commerce Decision Layer

**Status:** 26. august 2026  
**Repository:** `/Users/madsflyvholm/Desktop/decision layer`  
**Dokumentets scope:** Hele det videnskabelige Customer Twin-, Commercial Twin- og Decision Layer-produkt. Frontend er bevidst udeladt.

## 1. Kort konklusion

Repositoryet indeholder nu en omfattende, typed og leak-safe forskningsplatform for:

> Commerce data → Customer State → Opportunity → kandidat-handling → ACT / VERIFY / TEST / AVOID / CONTROL → randomiseret respons → Merchant Memory → bedre næste beslutning.

Følgende er dokumenteret:

- leak-safe forecasting, prediction freezing og evaluering;
- deterministisk e-commerce opportunity discovery;
- contribution-profit-baseret økonomi;
- randomiseret causal estimation og DR/AIPW;
- kontinuerlig dose-response-estimation med support og abstention;
- eksperimentdesign og hukommelse fra tidligere resultater;
- `MerchantLearningRecord`, der faktisk påvirker senere beslutninger;
- customer-level cross-fittede doubly robust action-scores;
- sikker policy-promotion mod Control;
- budgetteret exploration med kendte propensities;
- syntetiske, offentlige og real-observationelle valideringer;
- append-only Prediction Ledger og performance registry;
- preregistration, freeze og one-time final reveal i de nyeste benchmarks.

Det samlede produkt er **ikke valideret til kommercielle beslutninger endnu**. V4 er sikrere end V3, slår V3 og random targeting, men taber stadig klart til Control. Der findes ingen real merchant-evidens for profitabel personaliseret policy value.

## 2. Produktets videnskabelige grundregel

Systemet adskiller konsekvent:

1. **Descriptive:** Hvad er observeret?
2. **Predictive:** Hvad forventes at ske?
3. **Causal:** Hvad ændres af en bestemt handling under eksplicitte antagelser?
4. **Economic:** Skaber handlingen inkrementel contribution profit efter alle relevante omkostninger?
5. **Decision:** Er evidensen stærk nok til ACT, eller skal systemet TEST, VERIFY, AVOID eller vælge CONTROL?

Prediction accuracy er ikke causal accuracy. En observeret profitforskel er ikke automatisk en kausal effekt. Syntetisk oracle-truth må kun anvendes efter estimater og policies er frosset. CONTROL er en legitim og ofte korrekt beslutning.

## 3. Samlet produktarkitektur

```text
Commerce events og historik
        ↓
Data Trust + point-in-time materialisering
        ↓
Observed Customer State / Population State
        ↓
Prediction Engine + support/reliability
        ↓
Deterministisk Opportunity Engine
        ↓
Constrained Action Candidates
        ↓
Randomized Evidence + MerchantLearningRecord
        ↓
Causal/DR Action Scoring + Support + Uncertainty
        ↓
Contribution-profit Economics
        ↓
ACT / VERIFY / TEST / AVOID / CONTROL
        ↓
Experiment assignment med loggede propensities
        ↓
Realiseret causal og økonomisk respons
        ↓
Prediction Ledger + Merchant Memory
        ↓
Bedre eller mere konservativ næste beslutning
```

Estimation og økonomisk optimering er separate lag. Opportunity Engine identificerer et forretningsproblem, men definerer ikke automatisk behandlingspublikummet.

## 4. Datakontrakter og typed produktobjekter

Der er implementeret immutable Pydantic-kontrakter for blandt andet:

- `ObservedCustomerState`;
- `MerchantCustomerTwin`;
- `PopulationState`;
- `Opportunity`;
- `ActionCandidate`;
- `DecisionCard`;
- `ExperimentSpec`, arms, assignments og outcomes;
- `ExperimentResult`;
- `MerchantLearningRecord`;
- evidenslabels og health checks;
- forecasts, usikkerhedsintervaller og support;
- causal estimates, policy value og regret;
- model- og benchmarkresultater.

Kontrakterne håndhæver forskellen mellem observeret, predicted, randomized causal, observational causal, economic, simulated og insufficient evidence.

## 5. Data Trust og leakage-sikkerhed

Platformen indeholder:

- point-in-time filtrering på både event- og observationstid;
- halvåbne target-vinduer;
- cutoff-baseret featurematerialisering;
- expanding-window og rolling-origin splits;
- kronologiske og group-safe causal folds;
- strengt shiftede lag- og rolling-features;
- blokering af post-treatment features og mediatorer;
- feature allowlists og oracle isolation;
- prediction freeze før target reveal;
- hashes af konfiguration, data/state og predictions;
- one-time reveal-markører i officielle benchmarks.

Quick modes anvendes kun til pipelinevalidering. Officielle modelvalg og final targets må ikke afsløres i quick mode.

## 6. Customer State og Customer Twin

### Observeret state

Customer State samler blandt andet:

- lifecycle og tenure;
- recency, frequency og monetary/value;
- orders og purchase count;
- browsing-, cart- og checkout-signaler;
- recent intent;
- promotion exposure;
- refund/return-historik;
- category- og product affinity;
- cadence og support/reliability;
- tidligere treatments og tid siden seneste treatment.

### Dynamic Customer State

Der er udviklet:

- event-sequence/dynamics-modeller;
- calendar-time state;
- one-step og multi-step event prediction;
- population rollouts;
- cohort/state factories;
- hierarchical populationmodeller;
- Customer Population Engine V1, V2 og V3-forsøg;
- World State-kontrakter og completion-pass.

Resultatet er blandet. Behavioural information har signal, men kompakt state-sufficiency og kalibrerede population rollouts er ikke generelt demonstreret.

## 7. Prediction Engine

### Forecasting

Implementeret:

- sæsonbaselines;
- deterministic LightGBM point models;
- quantile models;
- quantile-crossing repair;
- split-conformal calibration;
- historisk performance-vægtede ensembles;
- MAE, RMSE, WAPE, MASE og pinball loss;
- coverage, interval width, WIS og empirisk CRPS;
- temporal drift og subgroup evaluation.

### Prediction Engine V2 / H&M Day-1

Den officielle H&M 12-måneders test omfattede 982.710 eksisterende kunder og 31,8 mio. transaktionslinjer.

| Mål | Resultat |
|---|---:|
| Final AUROC | 0,7414 |
| ECE | 0,0471 |
| Buyer-count error | 20,90% |
| Top-10 lift | 2,70× |
| Observed transaction-value error | 39,28% |

Ranking havde reel værdi, men ranking-, calibration-, aggregate-buyer-, subgroup- og monetary-gates fejlede. Samlet verdict: **NO** til day-1 readiness.

## 8. Opportunity Engine

V3 introducerede fem deterministiske opportunity-familier:

1. Repeat deterioration.
2. High-intent / low-conversion.
3. Discount / margin leakage.
4. Return / refund leakage.
5. Cohort / funnel deterioration.

Alle opportunities kræver:

- minimum sample size;
- legitim historisk baseline;
- persistence;
- minimum rate- og economic gap;
- uncertainty;
- data quality;
- temporal validity;
- Benjamini–Hochberg false-discovery control;
- economic-first prioritering.

Priority beregnes ud fra economic gap og robustness. En revenue-stigning med faldende contribution profit behandles som et problem. En LLM må forklare resultatet, men må ikke opfinde opportunityen.

### Planted discovery-test

Seks merchant-typer, 40 seeds pr. type og 240 officielle merchants:

| Metric | Resultat |
|---|---:|
| Precision | 100% |
| Recall | 100% |
| Null false-positive rate | 0% |
| Economic-weighted precision | 100% |
| Economic-weighted recall | 100% |
| Top-1 accuracy | 100% |

Verdict: **PASS på den klart separerede syntetiske fixture**. Det er komponentvalidering, ikke bevis for real-merchant discovery accuracy.

## 9. Action Candidate Engine og Decision Cards

Actions vælges fra en begrænset e-commerce-taxonomy:

- Control / no action;
- free shipping;
- shipping-threshold adjustment;
- discount-depth adjustment;
- targeted offer;
- bundle/multi-buy;
- retention treatment;
- merchandising/category intervention;
- investigate/verify.

Action-typen skal være relevant for opportunityen. Decision Cards samler opportunity, economic gap, evidence, support, uncertainty, candidate actions, anbefaling og eventuelt experiment plan.

## 10. Causal inference

### Diskrete treatments

Implementeret:

- difference-in-means og naive baselines;
- outcome regression;
- S- og T-learners;
- X-learner og challengers i modeltournaments;
- cross-fitted EconML DRLearner, hvor dependency er tilgængelig;
- AIPW/doubly robust estimation;
- known randomized propensities;
- propensity, overlap, ESS og balance diagnostics;
- direct, IPW og DR policy-value estimators;
- treatment-shuffle placebo;
- partial-R² sensitivity;
- estimator sign/rank agreement;
- development-only model selection og freeze før final test.

### Hillstrom RCT

64.000 randomiserede observationsrækker:

- Men's email spend ATE: 0,7837, 95% CI `[0,2327; 1,3567]`;
- Women's email spend ATE: 0,7425, 95% CI `[0,1066; 1,3919]`;
- learned policy slog Control med høj sandsynlighed;
- learned policy slog ikke bedste statiske treatment;
- personaliseret uplift-værdi blev derfor ikke demonstreret.

Verdict: **MIXED**.

### Layer 3 synthetic AIPW

Fem-fold cross-fitted AIPW over randomized, measured-confounded og placebo-scenarier:

- randomized adjusted bias cirka −0,000007;
- confounded adjusted RMSE 0,0066 mod naive 0,1014;
- 95% coverage 93–97%;
- placebo false-positive rate 4%;
- oracle truth blev først anvendt efter freeze i Prediction Ledger.

Verdict: **PASS som syntetisk metodevalidering**.

### Dunnhumby/Complete Journey

Real observational assignment, ikke RCT:

- adjusted ATE 0,0052;
- 95% CI `[-0,0230; 0,0334]`;
- control ESS 166;
- overlap og balance-gates fejlede;
- contribution profit kunne ikke beregnes på grund af manglende cost fields;
- første final blev burned efter en ugyldig propensity-implementation.

Verdict: **INSUFFICIENT**. Rendered answer: “We do not have enough evidence to answer this reliably.”

## 11. Kontinuerlig discount dose-response

Platformen indeholder:

- truth-known continuous retail DGP;
- measured og hidden confounding;
- good, weak og bad support;
- naive, elasticity og flexible outcome baselines;
- cross-fitted `ContinuousDRDoseResponseEstimator`;
- outcome nuisance og conditional treatment-density nuisance;
- localized/kernel DR correction;
- density clipping, clipped fraction, ESS og weight diagnostics;
- `ConditionalSupportGate` med conditional density, local ESS, kernel support, dose distance og extrapolation;
- bootstrap counterfactual uncertainty;
- calibration ved 50/80/90/95%;
- support-aware economics;
- robust near-optimal discount range;
- ACT / EXPERIMENT / ABSTAIN;
- falsification, placebos og sensitivity diagnostics;
- quick og definitive benchmark modes.

Den første definitive continuous-retail benchmark fejlede causal dose-response, calibration og abstention. Efterfølgende DR/support-passes forbedrede mekanismerne, men der foreligger ikke bevis for real observational continuous-discount readiness. Hidden confounding er eksplicit uløst; systemet må kun nedgradere evidens, ikke hævde identifikation.

## 12. Economics og policy optimization

Economics-laget beregner contribution profit ud fra relevante komponenter:

- gross/item sales;
- discounts;
- refunds/returns;
- COGS;
- merchant shipping cost;
- campaign variable cost;
- payment cost.

Derudover findes:

- Monte Carlo uncertainty propagation;
- risk-adjusted utility;
- lower-tail expected shortfall;
- margin- og business constraints;
- economic regret;
- experiment sizing;
- robust range frem for falsk decimalpræcision;
- baselines som Control, treat-all, treat-none og simple merchant policies.

V3 viste, at profitoptimering slog revenueoptimering med **+10.386,28**, 95% CI `[+9.723,50; +11.102,00]`.

## 13. Merchant Memory og closed-loop learning

Den vigtigste tidligere manglende mekanisme var, at `MerchantLearningRecord` blev skrevet, men ikke reelt påvirkede senere decisions. Det er nu rettet.

Memory indeholder:

- pre-action state;
- action definition;
- outcome definition;
- estimated effect;
- uncertainty og confidence interval;
- economics;
- evidence type;
- experiment ID og timestamp.

`HistoricalEvidenceMatcher` klassificerer:

- `HIGH_SUPPORT`;
- `PARTIAL_SUPPORT`;
- `STALE`;
- `OUT_OF_SUPPORT`.

Historisk evidens kan føre til:

- ACT ved stærk, relevant, frisk og downside-sikker evidens;
- VERIFY ved stale/shifted/partially supported evidence;
- TEST ved økonomisk mulighed uden tilstrækkelig kausal evidens;
- AVOID ved understøttet negativ inkrementel profit;
- CONTROL ved manglende dokumenteret upside.

V3 dokumenterede, at learning slog frozen med +1.794,54. V4 dokumenterede igen forbedring mod V3, men closed-loop learning skabte endnu ikke mere profit end Control.

## 14. Safe customer-level targeting V4

V4 ændrede alene Opportunity → Audience → Action-policyen.

### Cross-fittede DR action-scores

For randomized historical experiments estimeres:

```text
Gamma_i(a) = mu_a(X_i)
             + I(A_i=a)/p_a(X_i) * (Y_i - mu_a(X_i))

DeltaGamma_i(a) = Gamma_i(a) - Gamma_i(Control)
```

Hvor:

- `Y` er realiseret contribution profit;
- `p_a` er den loggede randomiseringspropensity;
- nuisance-predictions er cross-fittede;
- observational assignment bliver ikke opgraderet til randomized evidence;
- propensity clipping og ESS er synlige diagnostics.

### Policy learner

- shallow interpretable welfare tree, depth ≤3;
- honest train/evaluation split;
- Control er altid tilgængelig;
- policy value evalueres held-out mod Control;
- promotion kræver `LCB95[V(policy)-V(Control)] > 0`;
- personalization kræver desuden positiv held-out heterogeneity lower bound;
- ellers returneres population decision eller Control;
- unsupported, stale eller ustabile regions falder tilbage til Control.

### Exploration

- de første fire episoder opbygger randomiseret evidens;
- senere bruges 20% experiment pool;
- inden for poolen er allocation 80% Control, 10% free shipping og 10% discount;
- præcise propensities logges;
- deployment-observationer genbruges ikke som randomiseret evidens;
- recent fire-episode evidence styrer promotion under drift;
- treatment count og last-treatment age er observerede policy-features;
- latent fatigue og sande treatment sensitivities eksponeres ikke.

## 15. Benchmarkhistorik

### Decision Lab V1

15 verdener, 50 seeds/verden, 25.000 kunder og 26 episoder:

- Twin profit: 3.873.522,65;
- bedste baseline: 3.903.692,77;
- difference: −30.170,13, CI fuldt under nul;
- opportunity precision 98,60%;
- recall 73,37%;
- harmful rate 17,16%;
- closed-loop learning ikke demonstreret.

Verdict: **FAIL**.

### Decision Lab V2

Fem verdener, 30 seeds/verden, 3.000 kunder og 12 episoder:

- Learning Twin: 113.899,21;
- Frozen Twin: 122.182,32;
- Control: 128.336,61;
- Learning vs Frozen: −8.283,11;
- Full State vs RFM: ingen signifikant forskel;
- memory ændrede decisions, men gjorde dem ikke bedre.

Verdict: **FAIL**.

### E-commerce Decision Layer V3

Discovery bestod den plantede fixture. Decision-resultater:

| Policy | Profit |
|---|---:|
| Control | 128.613,54 |
| Merchant heuristic | 113.712,50 |
| Revenue optimizer | 113.712,50 |
| Frozen | 122.304,24 |
| Learning | 124.098,78 |
| Random opportunity learning | 128.854,79 |
| Oracle | 132.347,79 |

- Learning vs Frozen: +1.794,54;
- Learning vs bedste baseline: −4.514,76;
- opportunity-guided vs random eligible: −4.756,01;
- Full State vs RFM: tie;
- harmful rate: 3,81%.

Verdict: **FAIL**. Discovery var korrekt, men Opportunity → Audience → Action var forkert.

### E-commerce Decision Layer V4

V3 Oracle blev auditeret som **MYOPIC, NOT AN UPPER BOUND**. V4 anvendte en Control-inkluderende hindsight policy-envelope som evalueringsreference.

Officiel konfiguration: fem verdener, 20 nye seeds/verden, 2.000 kunder og 12 episoder.

| Policy | Profit |
|---|---:|
| Control | 86.410,02 |
| Merchant heuristic | 76.251,14 |
| Random eligible | 80.817,23 |
| V3 frozen | 82.244,34 |
| V4 Learning | 83.517,84 |
| Oracle-reference | 105.845,21 |

- V4 vs Control: **−2.892,19**, 95% CI `[−3.066,71; −2.704,49]`;
- V4 vs Random: **+2.700,61**, CI fuldt positivt;
- V4 vs V3: **+1.273,50**, CI fuldt positivt;
- Full State vs RFM: −20,76, CI inkluderer nul — **TIE**;
- treatment rate: 9,86%;
- harmful-action rate: 3,74%;
- false ACT rate: 0%;
- AUTOC: −0,0079;
- heterogeneity supported rate: 0%;
- top-20 ranking advantage: +0,1766 CP/kunde, men uden robust heterogenitetsevidens.

Per verden tabte V4 stadig til Control:

| Verden | V4 − Control |
|---|---:|
| Null | −3.883,92 |
| Free shipping winner | −1.400,69 |
| Discount revenue trap | −2.819,07 |
| Heterogeneous response | −3.248,49 |
| Temporal drift | −3.108,77 |

Verdicts:

- Targeting policy: **PARTIAL**;
- Safe decision policy: **PARTIAL**;
- Synthetic e-commerce value: **FAIL**;
- Real merchant evidence: **NONE**.

## 16. Customer Twin Research V1 — samlet evidens

| Lag | Resultat |
|---|---|
| Behavioral information | PASS på JDsearch evidence |
| Dynamic predictive state | PARTIAL |
| Population simulation | FAIL |
| Randomized action response | PARTIAL/UNPROVEN |
| Off-policy decision value | UNPROVEN |
| Longitudinal counterfactual simulation | Synthetic FAIL; real-world UNPROVEN |
| Economics | UNPROVEN uden cost fields |

Den samlede tekniske thesis fik verdict **NO**. Særligt population calibration, selective targeting value, fuld OPE, sequential DR og real longitudinal causal evidence mangler.

## 17. Datasæt og valideringskilder

Repositoryet indeholder kode, adapters eller eksperimenter for:

- Hillstrom RCT;
- Criteo uplift;
- Complete Journey / Dunnhumby;
- H&M;
- JDsearch;
- RetailRocket;
- Online Retail II;
- Open Bandit quick validation;
- MT-LIFT adapter/protokol, men primær download var blokeret;
- M5 og Dominick's schema/adapters;
- egne truth-known synthetic retail og sequential customer worlds.

Offentlige observational datasets må ikke omtales som randomized merchant evidence. Manglende COGS, shipping-, discount-, return- eller campaign-cost fields betyder, at contribution-profit policy value ikke er identificeret.

## 18. Prediction Ledger, registry og reproducerbarhed

Der er implementeret:

- append-only DuckDB Prediction Ledger;
- frozen predictions før target reveal;
- evaluation records;
- state-, config- og prediction-hashes;
- append-only `ModelPerformanceRegistry`;
- development-only model selection;
- frozen winner/configuration;
- official reveal markers;
- JSON, Markdown, CSV og Parquet benchmarkartefakter;
- deterministic seeds og common random numbers.

V1–V4 finaler må ikke tuneres efter reveal. V3-artefakter blev bevaret uændret under V4-auditten.

## 19. Robusthed og sikkerhed

Implementeret:

- PSI, KS og Wasserstein drift;
- propensity overlap, balance og ESS;
- density floors og clipping reports;
- shuffle-placebos og negative controls, hvor valide;
- specification/nuisance variation;
- temporal holdout;
- leave-group-out tests;
- sensitivity analysis;
- support boundaries og abstention;
- evidence scorecards med hard fails og warnings;
- uncertainty-aware ACT gates;
- explicit Control fallback;
- stale evidence → VERIFY/TEST;
- negative supported effects → AVOID;
- no demonstrated upside → CONTROL.

Systemet producerer ikke en kunstig samlet “causal confidence = 93%”. Evidens forbliver dekomponeret.

## 20. Centrale kodeområder

### Commercial/Customer Twin

- `src/commercial_twin/customer_twin_core.py`: customer-twin core.
- `src/commercial_twin/dynamic_customer_state.py`: dynamisk state.
- `src/commercial_twin/world_state.py`: world/population state.
- `src/commercial_twin/ecommerce_opportunities.py`: fem opportunity-familier og gates.
- `src/commercial_twin/merchant_validation/contracts.py`: produktkontrakter.
- `src/commercial_twin/merchant_validation/learning.py`: historical evidence matching.
- `src/commercial_twin/merchant_validation/service.py`: decision flow og memory consumption.
- `src/commercial_twin/safe_policy.py`: cross-fittede DR-scores og safe policy learner.
- `src/commercial_twin/prediction_v2/`: H&M Prediction Engine V2.

### Decision Engine

- `src/decision_engine/causal/`: discrete, continuous, DR, uplift og diagnostics.
- `src/decision_engine/decision/`: evidence, confidence, support, model selection og optimizer.
- `src/decision_engine/economics/`: profit og risk-adjusted utility.
- `src/decision_engine/forecasting/`: baselines, LightGBM, quantiles og ensembles.
- `src/decision_engine/uncertainty/`: conformal og continuous bootstrap.
- `src/decision_engine/robustness/`: drift, placebo og sensitivity.
- `src/decision_engine/ledger/`: append-only Prediction Ledger.
- `src/decision_engine/registry/`: performance registry.
- `src/decision_engine/benchmark/`: time-machine, Hillstrom, uplift og continuous retail.

### Nyeste benchmarks

- `benchmarks/ecommerce_decision_layer_v3/`: opportunity discovery og V3 decision test.
- `benchmarks/ecommerce_decision_layer_v4/`: safe targeting, held-out ranking og official V4.
- `benchmarks/customer_twin_decision_lab_v1/` og `v2/`: tidligere closed-loop tests.
- `benchmarks/customer_twin_research_v1/`: seks-lags research thesis.
- `benchmarks/hm_day1_v2/`: officiel 12-måneders H&M readiness.

## 21. Test- og kvalitetsstatus

Senest verificeret efter V4:

- `pytest -q`: **255 tests passed**;
- `ruff check .`: **All checks passed**;
- `mypy src`: **Success, 132 source files**;
- V4 official runtime: **490,69 sekunder**.

Testdækning omfatter blandt andet leakage, cross-fitting, deterministic seeds, propensity clipping, support, oracle isolation, experiment assignment, memory matching, ACT/TEST/AVOID/CONTROL, continuous DR, economics, ledger, forecasting, opportunity discovery, safe policy og held-out targeting.

## 22. Hvad produktet kan sige i dag

Det kan troværdigt sige:

- “Vi observerer et statistisk og økonomisk materielt problem i denne population.”
- “Dette er descriptive/predictive evidence, ikke automatisk causal evidence.”
- “Tidligere randomiseret evidens er relevant, delvist relevant, stale eller uden support.”
- “Den estimerede policy slår/Slår ikke Control på held-out evidence.”
- “Heterogenitet er/er ikke demonstreret.”
- “Vi anbefaler TEST/VERIFY/AVOID/CONTROL frem for unsupported ACT.”
- “Contribution profit kan ikke identificeres uden nødvendige omkostningsfelter.”

Det kan ikke troværdigt sige:

- “Customer Twin skaber dokumenteret mere profit end Control.”
- “Full Customer State er bedre end RFM til policy value.”
- “Personaliseret targeting skaber dokumenteret værdi.”
- “Population simulation er kalibreret nok til autonom drift.”
- “Observational commerce data beviser treatment effects uden antagelser.”
- “Real merchant profit impact er valideret.”
- “Produktet er production ready.”

## 23. Største resterende fejl

Den største fejl er ikke længere, at memory er frakoblet, eller at targeting aggressivt ACT'er uden evidens. Den største fejl er:

> Systemet kan endnu ikke finde tilstrækkeligt stærk og stabil treatment heterogeneity til, at værdien af en lært policy tilbagebetaler omkostningen ved sikker randomiseret exploration inden for benchmarkhorisonten.

V4 reducerer skade, har 0% false ACT, slår V3 og random eligible, men taber stadig til Control. Full State slår ikke RFM. Derfor er mere modelkompleksitet ikke fortjent af evidensen.

## 24. Samlet capability-verdict

| Capability | Verdict |
|---|---|
| Typed scientific architecture | PASS |
| Leakage safety og frozen evaluation | PASS |
| Prediction ranking | PARTIAL |
| Probability/population calibration | FAIL/PARTIAL afhængigt af dataset |
| Deterministisk opportunity discovery | PASS på planted synthetic fixture |
| Merchant memory påvirker decisions | PASS |
| Randomized causal estimator plumbing | PASS synthetic / PARTIAL public RCT |
| Continuous observational dose-response | IKKE KOMMERCIELT VALIDERET |
| Contribution-profit optimization | PASS som mekanisme |
| Profit vs revenue policy | PASS synthetic |
| Safe Control fallback | PASS som mekanisme |
| Heterogeneous targeting | FAIL/NOT DEMONSTRATED |
| Full State vs RFM | TIE |
| Learning vs V3/random | PASS i V4 |
| Learning vs Control | FAIL |
| Real merchant evidence | NONE |
| Production readiness | NO |

## 25. Endelig produktstatus

Repositoryet er en seriøs videnskabelig beslutnings- og valideringsplatform med stærke kontrakter, leakage controls, causal/economic separation, support-aware refusal og reproducerbare benchmarks. Det er ikke endnu et valideret autonomt commerce-produkt.

Den vigtigste positive udvikling fra V1 til V4 er:

1. Opportunities blev deterministiske og økonomisk prioriterede.
2. Merchant memory begyndte faktisk at påvirke næste decision.
3. Profitoptimering slog revenueoptimering.
4. Targeting blev flyttet fra coarse state matching til randomized DR policy learning.
5. Heterogeneity og policy value fik separate held-out gates.
6. False ACT blev reduceret til 0% i V4.
7. V4 slog V3 og random eligible klart.

Den afgørende negative konklusion er:

> **Nej, systemet har endnu ikke bevist, at det kan omsætte randomized historical commerce evidence til en customer-level policy, der skaber mere realiseret contribution profit end blot at vælge Control.**

Det er den korrekte nuværende videnskabelige status. Næste produktmæssige ret er ikke flere features, men stærkere eller længere randomiseret merchant evidence og en ny preregistreret test af, om exploration-omkostningen faktisk kan tilbagebetales.

