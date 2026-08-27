# Alt bygget: modelselektion og økonomisk policyvalidering

## Formål

Denne implementeringsrunde fjernede antagelsen om, at Commercial Twin DR automatisk er
den bedste eller foretrukne model.

Systemet vælger nu model separat for hver beslutningstype ud fra development-data. Den
valgte model og policy fryses, før det endelige testdatasæt evalueres. Kundevendt
`DO THIS` er samtidig gjort fail-closed og kan kun aktiveres, hvis den validerede gate
slår alle krævede alternativer på både development og urørt test.

Der er ikke tilføjet nye produktområder, integrationer eller mere World State.

## 1. Development-only modelselektion

Der er bygget en generisk, typed modelvælger til beslutningsspecifikke turneringer.

Vælgeren modtager for hver kandidat:

- modelnavn;
- development-policyværdi;
- development-kalibreringsfejl;
- den evaluerede policy;
- eventuel metadata.

Udvælgelsen sker i to trin:

1. Modeller uden for den eksplicitte kalibreringstolerance frasorteres.
2. Blandt de kvalificerede modeller vælges den højeste development-policyværdi.

Den frosne selektion registrerer:

- beslutningstype;
- valgt model;
- valgt policy;
- development-policyværdi;
- development-kalibrering;
- kvalificerede modeller;
- modeller afvist på kalibrering;
- tidspunkt for freeze;
- at testmetrics ikke blev brugt til selektion.

Det sidste felt er eksplicit `test_metrics_used_for_selection=false`.

## 2. Beslutningsspecifik modelregistry

ModelPerformanceRegistry er udvidet med empiriske standardmodeller per beslutningstype.

Det betyder eksempelvis:

- `binary_ad_targeting` kan vælge S-learner;
- `email_spend_capacity` kan vælge en anden model;
- `continuous_discount` påvirkes ikke automatisk af vinderne ovenfor.

En vinder i én kausal opgave bliver derfor ikke ukritisk genbrugt i en anden opgave med
et andet treatment, outcome eller identifikationsproblem.

## 3. Sammenlignede modeller

Turneringerne understøtter og sammenligner følgende relevante challengers:

- statisk/treat-all-baseline;
- outcome-model eller outcome-propensity-ranking;
- S-learner;
- T-learner;
- X-learner/effect learner;
- cross-fitted DRLearner;
- den tidligere Commercial Twin DR-konfiguration, hvor relevant.

Commercial Twin DR er nu en kandidat, ikke en privilegeret standardmodel.

## 4. Freeze før endelig test

Benchmarkforløbet er struktureret som:

1. Fit nuisance- og upliftmodeller på train.
2. Generér development-prediktioner.
3. Evaluer kalibrering og policyværdi på development.
4. Vælg model og policy.
5. Frys selektionen og gate-reglerne.
6. Evaluér derefter den frosne løsning på urørt test.

Development- og testprediktioner gemmes som frosne Parquet-filer. Prediction Ledger
registrerer datasæt, split, model, antal rækker, filsti, SHA-256, konfiguration og skjulte
outcome-kolonner.

Testresultatet bruges ikke til at skifte vinder, kapacitet eller gate efterfølgende.

## 5. Kundevendt gating

Den fælles gate sammenligner den gatede policy med:

- den valgte, ugatede policy;
- simpel targeting;
- treat-all;
- treat-none.

`DO THIS` kræver, at den gatede policy slår samtlige alternativer på både development og
endelig test.

Commercial Twin-præsentationen er ændret til fail-closed:

- intern `ACT` uden eksplicit valideret gate vises som `TEST THIS`;
- `DO THIS` vises kun ved
  `customer_facing_do_this_enabled=true` i evidensgrundlaget;
- `EXPERIMENT` vises som `TEST THIS`;
- `ABSTAIN` vises som `NOT ENOUGH EVIDENCE`.

Det forhindrer, at en intern disposition ved en fejl bliver til en stærk kundevendt
anbefaling.

## 6. Criteo randomized uplift benchmark

### Opsætning

Beslutningstype: `binary_ad_targeting`.

Den eksisterende definitive Criteo-turnering blev brugt med frosne development- og
testprediktioner. Den development-valgte policy var top 20% under en kapacitetsgrænse.

### Development-vinder

**S-learner** blev valgt. Commercial Twin DR vandt ikke.

| Metric | Resultat |
|---|---:|
| Development-policyværdi | 0.00299638 |
| Development-kalibreringsfejl | 0.00011589 |
| Final AUUC | 0.00330211 |
| Final Qini | 0.00054563 |
| Final kalibreringsfejl | 0.00008214 |
| Final top-20%-policyværdi | 0.00303335 |

Outcome propensity havde en højere rå development-policyværdi, men blev afvist af den
forhåndsdefinerede kalibreringstolerance. T-learner blev også afvist på kalibrering.

### Criteo-gate

På final test var policyværdierne:

| Policy | Værdi |
|---|---:|
| Gated S-learner | 0.00297796 |
| Ugated S-learner | 0.00306574 |
| Simpel targeting | 0.00302760 |
| Treat-all | 0.00307444 |
| Treat-none | 0.00188570 |

Gaten tilførte ikke værdi og slog ikke de krævede alternativer. `DO THIS` blev derfor
deaktiveret.

## 7. Anden randomized commerce benchmark

### Datasæt og treatment

Der er bygget en separat økonomisk benchmark på Hillstrom-RCT'en:

- treatment: Men's email;
- kontrol: ingen email;
- outcome: observeret kundespend;
- antal rækker: 42.613;
- train/development/test: 25.567 / 8.523 / 8.523.

### Økonomisk constraint

Benchmarkscenariet har:

- kontaktomkostning: **$0,50 per behandlet kunde**;
- maksimal behandlingskapacitet: **20%**;
- evaluerede kapaciteter: **5%, 10% og 20%**.

Kontaktomkostningen er en eksplicit benchmarkantagelse og ikke et felt i Hillstrom-data.
Dette fremgår af artefakter og rapportering.

Den estimerede policyværdi er:

```text
forventet økonomisk værdi
= RCT/IPW-estimeret kundespend under policy
- kontaktomkostning × behandlingsandel
```

Treatment propensity er 0,5 i det randomiserede eksperiment. Værdiestimatoren anvender
derfor inverse-probability weighting til at estimere værdien af en selektiv policy.

## 8. Hillstrom-modeller

Følgende kandidater blev fit på train:

- static treat-all;
- outcome-propensity Random Forest;
- S-learner Random Forest;
- T-learner med separate treatment- og kontrolmodeller;
- X/effect-learner;
- cross-fitted DRLearner.

DRLearnerens pseudo-outcome beregnes out-of-fold med separate outcome-modeller for
treatment og kontrol. En effektmodel fit'es derefter på de cross-fittede pseudo-outcomes.

## 9. Hillstrom development-selektion

Development valgte:

- model: **outcome propensity**;
- policy: **top 20%**;
- development-nettoværdi: **$0,93438 per kunde**;
- development-kalibreringsfejl: **$0,76971**.

S-, T-, X- og DR-learner blev afvist af development-kalibreringsfilteret. Den valgte
outcome-ranking er en simpel challenger og ikke en påstand om individuelt identificeret
kausal effekt.

## 10. Urørt Hillstrom-test

| Policy/metric | Resultat per kunde |
|---|---:|
| Frossen valgt policy, top 20% | $0,68098 |
| Treat-none | $0,68791 |
| Treat-all efter kontaktomkostning | $0,56305 |
| Tilfældig 20%-allokering | $0,66294 |
| Simpel targeting | $0,68098 |
| Test-bedste feasible challenger, top 10% | $0,81835 |
| Regret for den frosne policy | $0,13737 |

Yderligere testmetrics:

- kalibreringsfejl: **$1,18250**;
- AUUC: **0,00843**;
- Qini: **-0,03466**.

Den frosne policy slog en tilfældig 20%-allokering lidt, men den slog ikke treat-none og
var identisk med den definerede simple targeting-baseline. Selektiv targeting skabte
derfor ikke dokumenteret inkrementel økonomisk værdi.

Top-10%-policyen er kun identificeret efterfølgende som test-orakel til beregning af
regret. Den er ikke promoveret, og systemet er ikke retunet til den.

## 11. Hillstrom-gate

På development tabte den gatede policy til både den ugatede policy og treat-all. På test
var gated policy reelt treat-none og slog derfor heller ikke alle krævede alternativer
strikt.

Resultatet er:

- `customer_facing_do_this_enabled=false`;
- intern `TEST THIS` tilgængelig;
- intern `NOT ENOUGH EVIDENCE` tilgængelig.

## 12. Videnskabelig konklusion

| Capability | Verdict |
|---|---|
| Development-only modelvalg | PASS |
| Freeze før final test | PASS |
| Beslutningsspecifikke modeldefaults | PASS |
| DR behandles som challenger | PASS |
| Prediction Ledger og frosne prediktioner | PASS |
| Fail-closed kundevendt anbefaling | PASS |
| Criteo uplift-ranking | MIXED |
| Criteo-gate skaber ekstra værdi | FAIL |
| Hillstrom cost-constrained policy generaliserer | FAIL |
| Selektiv targeting slår simple alternativer | FAIL |
| Samlet success criterion | FAIL |

Systemet vælger nu empirisk blandt de tilgængelige modeller og nægter at vise `DO THIS`,
når evidensen ikke understøtter det. Men den anden økonomiske benchmark dokumenterer ikke,
at den frosne selektive policy slår simple alternativer på urørt test.

Dette er et reelt negativt resultat. Det blev ikke forsøgt repareret ved at tune på test.

## 13. Hvad der fortsat ikke er bevist

- At én upliftmodel er universelt bedst på tværs af beslutningstyper.
- At Hillstrom-development-vinderen er stabil ved nye stikprøver.
- At individuel email-effekt på spend er præcist kalibreret.
- At den antagne kontaktomkostning på $0,50 svarer til en bestemt virksomheds reelle cost.
- At selective targeting giver positiv inkrementel værdi i andre kapacitets- eller
  costscenarier.
- At en kundevendt `DO THIS`-gate skaber værdi. Den er derfor fortsat deaktiveret.

## 14. Oprettede filer

- `src/decision_engine/decision/model_selection.py`
- `scripts/select_criteo_decision_model.py`
- `src/decision_engine/benchmark/hillstrom_economic.py`
- `scripts/run_hillstrom_economic_benchmark.py`
- `tests/test_model_selection.py`
- `tests/test_hillstrom_economic.py`
- `docs/model_selection_and_economic_policy_validation.md`
- `docs/ALT_BYGGET_MODELSELEKTION_OG_OKONOMISK_POLICY.md`

## 15. Ændrede filer

- `src/decision_engine/registry/store.py`
- `src/commercial_twin/presentation.py`
- `tests/test_experiment_registry_dashboard.py`
- `tests/test_commercial_presentation.py`

## 16. Benchmarkartefakter

Criteo:

- `artifacts/benchmarks/criteo/definitive-seed-42-v2/development_model_selection.json`
- `artifacts/benchmarks/criteo/definitive-seed-42-v2/selected_model_product_view.json`
- frosne development- og testprediktioner for samtlige kandidater.

Hillstrom:

- `artifacts/benchmarks/hillstrom/economic-capacity-seed-42/summary.json`
- `development_policy_results.parquet`
- `final_policy_results.parquet`
- `selected_model_calibration.parquet`
- frosne development- og testprediktioner per model;
- `prediction_ledger.duckdb`;
- `model_registry.duckdb`.

## 17. Kvalitetskontrol

Efter implementeringen blev hele repository-kvalitetspakken kørt:

- `pytest -q`: **116 tests bestået**;
- `ruff check .`: **bestået**;
- `mypy src`: **bestået for 98 source-filer**.

Der var én ikke-funktionel joblib-advarsel om detektion af fysiske CPU-kerner. Den påvirkede
ikke testresultaterne.

## 18. Endeligt svar på målet

Commercial Twin kan nu vælge den bedst kvalificerede model på development uden at antage,
at DR er standard. Den kan fryse vinderen før test og tilbageholde kundevendt handling,
hvis en gate ikke slår simple alternativer.

Men den nuværende frosne, cost-constrained Hillstrom-policy slog ikke treat-none eller
simple targeting på urørt test. Derfor er den korrekte status:

**Modelselektion og sikker tilbageholdelse virker; dokumenteret selektiv økonomisk værdi
er endnu ikke opnået.**
