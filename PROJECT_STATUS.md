# Decision Engine — samlet projektstatus

**Statusdato:** 25. august 2026  
**Repository:** `/Users/madsflyvholm/Desktop/decision layer`  
**Pakkeversion:** `0.1.0`  
**Teknisk omfang:** 68 Python-kildefiler og ca. 4.136 kodelinjer på tværs af `src/`, `tests/`, `scripts/` og `apps/`.

## 1. Formål og videnskabeligt princip

Projektet er bygget som en library-first, leak-safe beslutningsmotor, der estimerer udfald under mulige handlinger og omsætter evidensen til økonomiske beslutninger. Første domæne er retail promotion, hvor målet er inkrementel dækningsprofit frem for alene salgsløft.

Systemet adskiller eksplicit fire spørgsmål:

1. **Prediction:** Hvad vil sandsynligvis ske ud fra observerede mønstre?
2. **Causal estimation:** Hvad ændrer sig faktisk som følge af en handling?
3. **Uncertainty:** Hvor usikre og kalibrerede er estimaterne?
4. **Decision:** Hvilken understøttet handling optimerer det valgte økonomiske mål?

Den centrale designregel er, at prognosepræcision ikke beviser kausal præcision. Kontrafaktiske udfald er ikke observeret i historiske data, og systemet må derfor ikke præsentere dem som ground truth. Kausale konklusioner kræver identifikationsantagelser, overlap/support-kontrol, robusthedsanalyser og helst randomiserede benchmarks.

## 2. Hvad der er implementeret

### 2.1 Datakontrakter og schemas

- Immutable Pydantic-kontrakter for beslutninger, prædiktioner, sandsynlighedsfordelinger, evidens, evalueringer og regret.
- Typed `DecisionClaim`-objekter, så konklusioner knyttes til den evidens, de faktisk understøttes af.
- Klare grænser mellem prognose-, kausal-, usikkerheds- og beslutningslag.
- Typeinformation eksponeret via `py.typed`.

### 2.2 Leak-safe forecasting

- `TimeMachineBenchmark`, der filtrerer både på event-tid og observationstid.
- Historikken fryses ved cutoff; en prediction skal låses og persisteres, før udfald kan afsløres.
- Expanding-window og rolling-origin splits; ingen random split til tidsserier.
- Strengt shiftede lag- og rolling-features for at undgå target leakage.
- Fire altid aktive sæsonbaselines.
- Deterministiske LightGBM point- og kvantilmodeller.
- Monoton kvantilreparation og rapportering af quantile crossing.
- Kronologisk split-conformal justering.
- Historisk performance-baseret ensemblevægtning.
- Mål: MAE, RMSE, WAPE, MASE, pinball loss, interval coverage, interval width, weighted interval score og empirisk CRPS.

### 2.3 Causal inference for diskrete behandlinger

- Syntetisk confounded causal DGP.
- Naive estimators, outcome regression, S-learner og T-learner.
- Cross-fitted EconML DRLearner som valgfri estimator, når causal extras er installeret.
- Kronologiske causal folds.
- Overlap-, propensity-, effective-sample-size- og balance-diagnostik.
- Estimator agreement på fortegn og rangering.
- Direct, IPW og doubly robust policy-value estimators.
- Grouped treatment-shuffle placebo tests.
- Linear partial-\(R^2\)-sensitivitetsanalyse.
- Negative controls rapporteres som `NOT_AVAILABLE`, indtil en fagligt forsvarlig kontrol er defineret.

### 2.4 Kontinuerlig behandling og rabatoptimering

- Kontinuerlig treatment-estimator med naive, elasticity og flexible outcome-regression-varianter.
- Eksplicit blokering af post-treatment features.
- Gaussian generalized propensity score-diagnostik.
- Kernel-lokal dose support.
- Support-aware beslutningsmotor, der kan vælge `ACT`, `EXPERIMENT` eller `ABSTAIN`.
- En recommendation tilbageholdes, hvis det ukonstraintede optimum ligger uden for observeret support.
- Metrics for dose-response RMSE, integrated absolute/squared error, optimal-discount MAE og økonomisk regret.
- Spillover-metrics er implementeret, selv om en spillover-estimator endnu ikke indgår i tournamentet.

### 2.5 Økonomi og beslutninger

- Contribution-profit beregninger.
- Empirisk og model-residual Monte Carlo propagation.
- Risk-adjusted utility og lower-tail expected shortfall.
- Konfigurerbare constraints.
- Transparent confidence/evidence gate.
- Eksplicit refusal/withholding ved utilstrækkelig evidens.
- Regret-beregninger og sammenligning af policies.
- To-arm experiment sizing som alternativ til at handle på svag evidens.

### 2.6 Robusthed, drift og evidens

- PSI, Wasserstein og KS drift-diagnostik.
- Placebo- og falsifikationstests.
- Sensitivitetsanalyse for confounding.
- Evidens-scorecard med hårde fejl og advarsler.
- Estimator sign/rank agreement.
- Manglende evidens markeres som `NOT_AVAILABLE` frem for at blive udfyldt med antagelser.

### 2.7 Persistens og reproducerbarhed

- Append-only DuckDB prediction/evaluation ledger.
- Konfigurations- og state-hashes.
- Append-only model-performance registry.
- Benchmark-resultater gemmes som Markdown, JSON, Parquet og DuckDB.
- Seeds og benchmark-konfigurationer er eksplicitte for reproducerbare runs.

### 2.8 Research cockpit

Et lokalt Streamlit-dashboard er implementeret i `apps/research_dashboard.py`. Det åbner med et deterministisk syntetisk panel mærket **SYNTHETIC — NOT COMMERCIAL EVIDENCE** og indeholder visninger for:

- data health;
- time-machine cutoff;
- historisk baserede forecast weights;
- probabilistisk kalibrering;
- drift og falsifikation;
- transparent evidence scorecard;
- decision withholding;
- ledger-status;
- Hillstrom-resultater;
- continuous-retail benchmark-resultater.

Kør dashboardet med:

```bash
uv run streamlit run apps/research_dashboard.py
```

## 3. Datasæt og adapters

### Hillstrom

Det reelle Hillstrom email-marketingdatasæt er hentet og ligger i `data/raw/hillstrom/hillstrom.csv`.

- Rækker: **64.000**
- Mænd-email: **21.307**
- Kvinder-email: **21.387**
- Ingen email: **21.306**
- SHA256: `27bab8c5d3669f26ec08ebb50a0a78317542f29501156f2e2af6781fab4cd7e2`

### Øvrige adapters

- **M5:** adapter og forventet schema er implementeret; officielle filer skal leveres manuelt.
- **Dominick's:** schema-first adapter er implementeret, men reelle data er ikke tilgængelige i repository’et.
- **Dunnhumby:** availability/schema adapter er implementeret, men reelle data er ikke tilgængelige i repository’et.
- Downloadlogik omgår ikke authentication, licensvilkår eller distributørkrav.

## 4. Definitiv Hillstrom-benchmark

Den definitive kørsel findes i:

`artifacts/benchmarks/hillstrom/definitive-seed-42-bootstrap-2000/`

### Design

- Randomiseret multi-arm benchmark.
- Stratificeret 60/20/20 train/validation/test split: 38.400 / 12.800 / 12.800 rækker.
- Seed 42.
- 2.000 bootstrap-gentagelser.
- Leakage audit: **PASS**.
- Maksimal absolut standardized mean difference: **0,0181**.
- Primær anbefalet handling: **MENS_EMAIL**.

### Eksperimentelle effekter på testdata

| Handling | Udfald | ATE | 95 % CI |
|---|---:|---:|---:|
| MENS_EMAIL | Spend | 0,7837 | [0,2327; 1,3567] |
| WOMENS_EMAIL | Spend | 0,7425 | [0,1066; 1,3919] |
| MENS_EMAIL | Conversion | 0,00610 | [0,00211; 0,01009] |
| WOMENS_EMAIL | Conversion | 0,00348 | [-0,00026; 0,00746] |

### Estimator tournament

- Difference-in-means matcher per konstruktion den eksperimentelle ATE.
- Outcome regression havde absolut ATE-fejl **0,0097** for MENS_EMAIL og **0,3123** for WOMENS_EMAIL.
- S-learner havde absolut ATE-fejl **0,0427** og **0,3490**.
- T-learner havde absolut ATE-fejl **0,0883** og **0,3520**.
- Alle modeller fik korrekt fortegn.
- Estimator agreement blev vurderet **STRONG** med fuld sign agreement og praktisk talt fuld rank agreement.

### Policy value

| Policy | Direct | IPW | Doubly robust |
|---|---:|---:|---:|
| ALWAYS_CONTROL | 0,6619 | 0,5704 | 0,5714 |
| ALWAYS_MEN | 1,4553 | 1,3543 | 1,3494 |
| ALWAYS_WOMEN | 1,0921 | 1,3128 | 1,3165 |
| LEARNED_POLICY | 1,4553 | 1,3543 | 1,3494 |

- Bootstrap-sandsynlighed for, at learned policy slår control: **99,55 %**.
- Sandsynlighed for, at learned policy slår bedste statiske policy: **0 %**.
- Learned policy kollapsede derfor til den bedste statiske handling, MENS_EMAIL; der blev ikke dokumenteret ekstra værdi fra personalisering.
- Placebo tests: **PASS**.
- Samlet Hillstrom-vurdering: **MIXED** — stærk evidens for behandlingsrangering og policy-værdi, men ikke for individuel uplift/personaliseret heterogenitet.

## 5. Syntetisk continuous-retail world

Der er bygget en truth-known retail-panelgenerator med:

- butikker, kategorier, SKU’er og dage;
- hierarkiske base-demand- og treatment-parametre;
- ikke-lineær respons \(\exp(\beta d - \gamma d^2)\);
- confounded observationel rabattildeling;
- good, weak og bad support-regimer med maksimumrabatter på henholdsvis 30 %, 15 % og 4 %;
- valgfri hidden confounding;
- stockouts;
- post-treatment mediator;
- sparse cross-SKU interaction/spillover matrix;
- dynamisk kernel til pull-forward-effekter;
- fysisk adskilte truth-arrays, som ikke kan bruges som estimator-features.

## 6. Definitiv continuous-retail benchmark

Den definitive kørsel findes i:

`artifacts/benchmarks/continuous-retail/definitive-20-worlds-v3/`

### Design

- 20 truth-known syntetiske panelverdener.
- Good, weak og bad support-regimer.
- Kronologisk 70/30 split.
- Dose-grid fra 0 % til 30 % i trin på 2 procentpoint.
- Tre estimatorer: naive, elasticity og flexible.
- Truth-arrays bruges kun til evaluering og aldrig som features.
- Samlet runtime cirka **11,6 sekunder**.

### Aggregerede resultater

| Estimator | Regime | Dose RMSE | Integrated squared error | Optimal discount MAE | Economic regret | Abstention |
|---|---|---:|---:|---:|---:|---:|
| Elasticity | Bad | 2,2489 | 1,6206 | 0,0365 | 2,4390 | 0 % |
| Elasticity | Good | 1,8168 | 1,0285 | 0,0411 | 3,8085 | 0 % |
| Elasticity | Weak | 1,8874 | 1,0760 | 0,0381 | 2,5023 | 0 % |
| Flexible | Bad | 2,8596 | 2,5320 | 0,0342 | 2,1830 | 0 % |
| Flexible | Good | **1,4159** | **0,6432** | **0,0277** | 1,9029 | 0 % |
| Flexible | Weak | **1,7331** | **0,9151** | **0,0294** | **1,6292** | 0 % |
| Naive | Bad | 5,7052 | 10,8699 | 0,0368 | 2,4359 | 0 % |
| Naive | Good | 4,9918 | 7,9717 | 0,0404 | 3,4860 | 0 % |
| Naive | Weak | 4,7936 | 7,2574 | 0,0414 | 2,9256 | 0 % |

Flexible outcome regression er bedst på dose-recovery i good og weak support, men benchmarken viser samtidig, at modellerne ikke endnu kan forsvares som robuste kontinuerlige kausale estimatorer.

### Capability verdict

| Kapabilitet | Resultat |
|---|---|
| Baseline demand | MIXED |
| Causal dose-response | FAIL |
| Optimal discount recovery | MIXED |
| Hierarchical generalization | MIXED |
| Spillovers | MIXED |
| Dynamic effects | MIXED |
| Calibration | FAIL |
| Abstention | FAIL |
| Economic policy | MIXED |
| **Samlet** | **FAIL** |

FAIL-resultatet er tilsigtet og vigtigt: benchmarken måler evnerne ærligt og godkender ikke systemet, bare fordi infrastrukturen virker.

## 7. Test og kvalitetsstatus

Senest verificerede status før dette dokument:

- `pytest -q`: **44 tests passed**.
- `ruff check .`: **All checks passed**.
- `mypy`: **Success**, ingen typefejl i 68 source files.
- Reproducerbarheds-, leakage-, ledger-, causal-, forecasting-, uncertainty-, economics-, robustness-, dashboard- og continuous-retail-tests er dækket.
- Mappen er ikke initialiseret som et Git-repository; der findes derfor ingen commit-historik eller Git-status at rapportere.

## 8. Scripts og centrale kommandoer

### Installation

```bash
python -m venv .venv
source .venv/bin/activate
pip install -e '.[dev]'
```

For valgfrie causal dependencies:

```bash
pip install -e '.[causal,dev]'
```

### Verifikation

```bash
.venv/bin/pytest -q
.venv/bin/ruff check .
.venv/bin/mypy
```

### Benchmarks

```bash
python scripts/run_forecast_benchmark.py data/processed/series.parquet \
  --cutoff 2015-01-01T00:00:00+00:00 --horizon 7
python scripts/run_causal_benchmark.py
python scripts/run_decision_benchmark.py
python scripts/run_hillstrom_benchmark.py
python scripts/run_continuous_retail_benchmark.py
```

### Dataset-håndtering

```bash
python scripts/download_datasets.py
```

Scriptet respekterer datakilders authentication, licenser og distributionskrav.

## 9. Repository-struktur

```text
apps/                       Streamlit research cockpit
artifacts/benchmarks/       Reproducerbare rapporter, tabeller og ledgers
configs/                    Default-konfiguration
data/raw/hillstrom/         Hillstrom-kildedata
scripts/                    Benchmark- og dataset-entrypoints
src/decision_engine/
  benchmark/                Splits, time machine og benchmark-runners
  causal/                   Diskrete og kontinuerlige causal estimators
  dashboard/                Datatilgang til cockpit
  datasets/                 Datasæt-adapters og schemas
  decision/                 Claims, evidence, confidence og optimizers
  economics/                Profit og utility
  features/                 Temporal features og leakage guards
  forecasting/              Baselines, LightGBM, quantiles og ensembles
  ledger/                   Append-only prediction/evaluation ledger
  metrics/                  Forecasting, causal, probabilistic og decision metrics
  registry/                 Model-performance registry
  robustness/               Drift, placebo og sensitivity
  simulation/               Monte Carlo
  synthetic/retail/         Truth-known continuous retail world
  uncertainty/              Quantile- og conformal-værktøjer
tests/                      44 automatiserede tests
```

## 10. Hvad resultaterne kan og ikke kan bruges til

### Forsvarligt understøttet nu

- Leak-safe, reproducerbar forecasting- og benchmarkinfrastruktur.
- Transparent separation af prediction, causal inference, uncertainty og decision.
- Evidensbaseret refusal frem for skjult ekstrapolation.
- Korrekt identifikation af MENS_EMAIL som bedste statiske Hillstrom-policy.
- Robust benchmark-, ledger- og registry-infrastruktur.
- Truth-known testmiljø for continuous discount policies.

### Ikke endnu forsvarligt understøttet

- At de nuværende continuous outcome models er egentlige kontinuerlige kausale estimatorer.
- Korrektion for hidden confounding i continuous-retail-verdenen.
- GPS bruges som diagnostik, ikke som fuldt estimator-led.
- Spillover- og dynamiske effekter genereres som truth, men estimeres ikke i tournamentet.
- Counterfactual interval calibration, coverage og WIS for continuous treatment.
- Valideret individualiseret uplift på Hillstrom.
- Kommercielle beslutninger på Dominick's eller Dunnhumby uden de reelle datasæt.
- Automatisk multi-entity recursive LightGBM forecasting i den nuværende forecast-CLI.
- At confidence score kan fortolkes som en kalibreret sandsynlighed for korrekthed.

## 11. Kendte videnskabelige og tekniske begrænsninger

1. **Continuous causal identification:** Naive, elasticity og flexible outcome regression kan være biased under confounding.
2. **Hidden confounding:** DGP’en kan generere skjult confounding, men de nuværende estimatorer korrigerer ikke for den.
3. **Support/abstention:** En eksplicit unsupported-dose test abstainer, men den definitive benchmark havde 0 % aggregeret abstention i alle regimer; capability-vurderingen er derfor FAIL.
4. **Calibration:** Der findes endnu ingen bootstrap- eller influence-function-baserede kontrafaktiske intervaller for dose-response.
5. **Spillovers:** Truth og metrics eksisterer, men ingen estimator benchmarkes.
6. **Dynamic effects:** Pull-forward-kernel eksisterer, men ingen kausal dynamisk estimator benchmarkes.
7. **Hierarchical pooling:** Partial pooling er demonstreret i en kontrolleret fixture, men ikke som fuld tournament-estimator.
8. **Forecast CLI:** LightGBM-wrappers er implementeret, men ikke fuldt koblet til en global, rekursiv multi-entity runner.
9. **Distribution shift:** Split-conformal kan miste coverage under tidsvarierende datagenerering.
10. **Economic validity:** Anbefalinger er kun så gyldige som costs, marginer, constraints, support og kausale antagelser.

## 12. Anbefalet næste udviklingstrin

Det højeste værditrin er en **cross-fitted continuous orthogonal/doubly robust estimator** med:

1. nuisance-modeller for outcome og treatment density;
2. density clipping og effective-sample-size-diagnostik;
3. strengt kronologiske folds;
4. dose-placebos og relevante negative controls;
5. bootstrap- eller influence-function-intervaller;
6. coverage, width og WIS på truth-known counterfactual curves;
7. eksplicitte support-thresholds, der producerer meningsfuld `ACT`/`EXPERIMENT`/`ABSTAIN`-adfærd;
8. benchmark mod naive, elasticity og flexible modeller i de samme 20 verdener;
9. separat evaluering under measured versus hidden confounding;
10. derefter real-data validering på Dominick's eller Dunnhumby, når data er lovligt tilgængelige.

Et parallelt forecasting-spor bør bagefter koble de eksisterende LightGBM-wrappers til en global rolling-origin multi-SKU/store benchmark med kronologisk kalibrering og frosne ledger-records.

## 13. Samlet konklusion

Repository’et er nu en sammenhængende videnskabelig beslutningsmotor med leak-safe backtesting, probabilistisk forecasting, diskret og kontinuerlig causal infrastruktur, økonomisk optimering, robustness diagnostics, evidensgating, append-only ledgers og et research cockpit.

Den stærkeste empiriske leverance er Hillstrom-benchmarken, som under randomisering dokumenterer, at MENS_EMAIL er den bedste statiske policy, men ikke at personalisering skaber ekstra værdi. Continuous-retail-sporet leverer et avanceret truth-known testlaboratorium og afslører samtidig ærligt, at continuous causal dose-response, calibration og operationel abstention endnu ikke består. Projektets vigtigste kvalitet er derfor ikke kun, hvad det kan anbefale, men også at det eksplicit viser, hvad evidensen endnu ikke tillader systemet at påstå.

## 14. Continuous DR v4

Den næste scientific pass implementerede en reel `ContinuousDRDoseResponseEstimator` med:

- strengt kronologisk cross-fitting;
- outcome nuisances: parametric og flexible;
- treatment-density nuisances: Gaussian og flexible residual-KDE;
- kernel-lokal inverse-density residualkorrektion;
- synlig density clipping, inverse weights og ESS;
- deterministic store-SKU clustered bootstrap;
- 50/80/90/95 % counterfactual demand-intervaller og profit draws;
- measured og hidden confounding rapporteret separat;
- support-stratificeret coverage, width og interval score.

Treatment density blev dermed en del af DR-estimatet frem for kun diagnostik. Oracle truth forblev evaluation-only.

V4 quick benchmark fandt:

| Resultat | Værdi |
|---|---:|
| DR wins vs naive, measured | 3/3 |
| DR wins vs flexible, measured | 3/3 |
| DR wins vs elasticity, measured | 1/3 |
| Measured 90 % coverage, supported/limited | 94,4 % |
| Hidden 90 % coverage | 63,2 % |
| Unsupported ACT | 0 |
| ACT / EXPERIMENT / ABSTAIN | 0 / 2 / 4 |
| Runtime | 102,85 s |

Verdict var MIXED for causal recovery og calibration, FAIL for operational abstention og samlet FAIL. Den komplette rapport er [docs/continuous_dr_v4_report.md](/Users/madsflyvholm/Desktop/decision%20layer/docs/continuous_dr_v4_report.md).

## 15. ConditionalSupportGate v5

V4’s umiddelbare problem var 100 % withholding. V5 byggede en fuld support failure trace og fandt, at problemet ikke alene var positivity:

- local ESS under `strong_local_ess=60` gav altid LIMITED;
- LIMITED fungerede for meget som et veto;
- support- og evidensårsager blev blandet;
- measured good seed 0 havde kun ca. 0,72 % estimeret profitfordel;
- hidden good seed 3 foretrak 0 %, havde overlappende intervaller og hidden-confounding warning;
- en geometri-bug brugte `context_weight > median`, så ens vægte kunne give nul comparables og nearest distance `∞`. Det er rettet til `>=`.

### Nye supportdiagnostikker

- raw conditional density;
- density percentile relativt til observed densities;
- density ratio to typical;
- context ESS og kernel ESS;
- nearest comparable dose og local dose spacing;
- conditional weighted 1–99 % dose region;
- extrapolation distance;
- clipping status;
- outcome-model disagreement;
- DR specification disagreement;
- hver rule, threshold og severity;
- separate hard failures og soft warnings.

Raw density rapporteres fortsat, men en scale-dependent absolut density threshold styrer ikke support alene.

### Frosne supportregler

| Regel | Threshold | Type |
|---|---:|---|
| Density percentile | < 1 % | HARD |
| Density percentile | < 5 % | SOFT |
| Density ratio | < 0,02 | HARD |
| Local/kernel ESS | < 5 | HARD |
| Local/kernel ESS | < 20 | SOFT |
| Local/kernel ESS | < 60 | SOFT |
| Nearest dose | > 0,04 | HARD |
| Nearest dose | > 0,025 | SOFT |
| Extrapolation | > 2,5 bandwidths | HARD |
| Invalid/effectively zero density | true | HARD |

En enkelt soft warning kan ikke længere blokere ACT. Support-, evidence- og withholding-årsager persisteres separat.

### Near-optimal supported projection

Et unsupported optimum kan kun projiceres til en nearby supported candidate, når:

- profittabet er højst 1 %;
- dose-afstanden er højst 0,04;
- den valgte candidate selv har support.

Distant boundary projection forbliver forbudt og testet.

### Gate-ablations

Syv ablations blev kørt: density only, ESS only, geometry only, extrapolation only, density+ESS, density+geometry og full gate. Alle havde 0 unsupported ACT. Ablationerne isolerede ESS som den aktive supportbegrænsning; density, geometri og extrapolation var ikke årsagen til good-world withholding.

### V5-resultater

Artifact: `artifacts/benchmarks/continuous-retail/quick-support-gate-v5-final/`

| Metric | V4 | V5 |
|---|---:|---:|
| ACT / EXPERIMENT / ABSTAIN | 0 / 2 / 4 | 1 / 2 / 3 |
| Good withholding | 100 % | 100 % |
| Weak withholding | 100 % | 50 % |
| Bad withholding | 100 % | 100 % |
| Unsupported ACT | 0 | 0 |
| Coarse false withholding | 100 % | 83,3 % |
| Measured DR RMSE | 2,314 | 2,314 |
| Measured 90 % coverage | 94,4 % | 100 % |
| Mean measured regret | 1,979 | 1,979 |
| Runtime | 102,85 s | 175,44 s |

Den nye ACT var 6 % i measured weak-support seed 1. Den havde ingen hard failures, én `moderate_ess` warning, density percentile 10,1 %, local ESS 50,55, estimeret profitfordel 2,779 og post-hoc oracle regret 0,683.

Good measured seed 0 gik fra ABSTAIN til EXPERIMENT. Good hidden seed 3 forblev ABSTAIN af evidensgrunde. Der kom ingen good-support ACT, så operational abstention og samlet verdict forblev FAIL. Definitive mode blev derfor ikke kørt.

Den komplette rapport er [docs/support_gate_v5_report.md](/Users/madsflyvholm/Desktop/decision%20layer/docs/support_gate_v5_report.md).

## 16. Aktuel kvalitet og samlet konklusion

- `pytest -q`: **64 passed**.
- `ruff check .`: **passed**.
- `mypy`: **passed** for 70 source files.
- Unsupported optimum → ACT er fortsat præcis 0.

Motoren har nu continuous DR, treatment-density correction, chronological cross-fitting, clustered counterfactual bootstrap, conditional support regions, hard/soft rules, gate-ablations, complete failure traces og sikker near-optimal projection. Den kan frembringe supported ACT og gjorde det én gang i v5 quick benchmark uden unsupported ACT.

Den har dog endnu ikke demonstreret good-support ACT i benchmarken, og hidden-confounding calibration er fortsat utilstrækkelig. Projektet er derfor ikke klar til definitive continuous-discount claims eller real retail pricing deployment. Næste smalle trin er held-out good-support evaluering med de nu frosne regler—ikke at løsne thresholds mod oracle-resultater.
