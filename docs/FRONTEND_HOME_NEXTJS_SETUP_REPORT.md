# Commercial Twin Home — Next.js Setup Report

**Dato:** 26. august 2026  
**Repository:** `/Users/madsflyvholm/Desktop/decision layer`  
**Status:** Implementeret og verificeret

## 1. Formål

Den eksisterende `home.tsx` kunne ikke åbnes med `npm run dev`, fordi repository-roden ikke indeholdt et JavaScript-/Next.js-projekt eller en `package.json`.

Denne ændring gør landingssiden tilgængelig som en lokal Next.js-side på:

```text
http://localhost:3000
```

Arbejdet er alene en minimal runtime- og routingopsætning omkring den eksisterende landingsside. Den videnskabelige Python-kode, beslutningsmotoren, benchmarks, datamodellerne og produktets øvrige arkitektur er ikke redesignet eller ændret.

## 2. Oprindelig fejl

Følgende kommando fejlede:

```bash
npm run dev
```

med:

```text
npm error code ENOENT
npm error path /Users/madsflyvholm/Desktop/decision layer/package.json
npm error enoent Could not read package.json
```

Årsagen var, at npm ikke kunne finde en `package.json` i repository-roden.

## 3. Implementeret løsning

Der er oprettet en minimal Next.js App Router-applikation, som genbruger den eksisterende `home.tsx` direkte.

Routingforløbet er:

```text
GET /
  -> app/page.tsx
  -> importerer Home fra home.tsx
  -> renderer Commercial Twin-landingssiden
```

`home.tsx` er markeret som en client component, fordi komponenten anvender React-hooks og browseradfærd.

## 4. Filer oprettet

### `package.json`

Definerer projektet, afhængighederne og kommandoerne:

```json
{
  "scripts": {
    "dev": "next dev",
    "build": "next build",
    "start": "next start"
  }
}
```

Installerede runtime-afhængigheder:

- Next.js `16.1.6`
- React `19.2.4`
- React DOM `19.2.4`

Installerede udviklingsafhængigheder:

- TypeScript
- Node.js-typer
- React-typer
- React DOM-typer

### `app/page.tsx`

Opretter root-ruten `/` og renderer den eksisterende `Home`-komponent fra `home.tsx`.

### `app/layout.tsx`

Opretter Next.js-rootlayoutet og definerer metadata:

- Titel: `Commercial Twin`
- Beskrivelse: `See the likely commercial outcome before you act.`
- Dokumentets sprog: engelsk

### `app/globals.css`

Tilføjer kun et lille globalt fundament:

- nulstiller body-margin
- sikrer fuld minimumshøjde
- sætter sidens grundfarve
- aktiverer smooth scrolling
- lader formularfelter arve typografi

Landingssidens eksisterende design og komponentnære CSS er fortsat bevaret i `home.tsx`.

### `tsconfig.json`

Aktiverer en strict TypeScript-konfiguration til Next.js med blandt andet:

- `strict: true`
- `noEmit: true`
- bundler module resolution
- Next.js TypeScript-plugin
- genererede Next.js route-typer

### `next-env.d.ts`

Tilføjer de typehenvisninger, som Next.js kræver.

### `.gitignore`

Ignorerer genererede frontendfiler:

- `node_modules/`
- `.next/`
- npm debug-logs

### `package-lock.json`

Låser de installerede npm-versioner, så installationen kan reproduceres.

## 5. Fil ændret

### `home.tsx`

Følgende direktiv er tilføjet øverst:

```tsx
"use client";
```

Det er nødvendigt, fordi siden anvender:

- `useState`
- `useEffect`
- `useRef`
- interaktive knapper og navigation
- browserbaserede animationer og tilstandsændringer

Den eksisterende visuelle implementering og produkttekst er ellers bevaret.

## 6. Tilgængelige kommandoer

### Lokal udvikling

```bash
cd "/Users/madsflyvholm/Desktop/decision layer"
npm run dev
```

Siden kan derefter åbnes på:

```text
http://localhost:3000
```

### Produktionsbuild

```bash
npm run build
```

### Start af et færdigt produktionsbuild

```bash
npm run start
```

Dette kræver, at `npm run build` allerede er kørt.

## 7. Verifikation

Følgende er kontrolleret efter implementeringen:

| Kontrol | Resultat |
|---|---|
| `npm install` | Bestået |
| `npm run build` | Bestået |
| TypeScript-kompilering | Bestået som del af Next.js-buildet |
| Next.js development server | Starter korrekt |
| Root-rute `/` | HTTP 200 |
| Sidekomponent | `home.tsx` indlæses via `app/page.tsx` |
| Dokumenttitel | `Commercial Twin` |
| Statisk produktionsrute | `/` genereres korrekt |

Observeret udviklingsserver:

```text
Next.js 16.1.6 (Turbopack)
Local: http://localhost:3000
Ready
GET / 200
```

## 8. Bevidst ikke ændret

Dette frontend-setup har ikke ændret eller udvidet:

- Continuous DR-estimatoren
- support- og evidensgating
- ACT / EXPERIMENT / ABSTAIN-logik
- økonomisk optimering
- Customer Twin Core
- Commercial Twin-modelselektion
- syntetiske eller virkelige datasæt
- benchmarks og benchmarkartefakter
- Prediction Ledger eller model registry
- dashboardets videnskabelige funktionalitet
- Shopify eller andre eksterne integrationer

## 9. Samlet resultat

Repository-roden fungerer nu både som den eksisterende videnskabelige Python-kodebase og som en minimal lokal Next.js-applikation. Den allerede byggede `home.tsx` kan vises direkte med `npm run dev`, uden at landingssiden eller den underliggende beslutningsmotor er blevet redesignet.

