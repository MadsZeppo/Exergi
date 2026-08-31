# Clerk + Shopify deployment checklist

This checklist deploys the reviewed code. It does not claim a live installation until the final
development-store reconciliation passes. Never paste secrets into chat, screenshots, Git or logs.

## 1. Clerk (manual)

1. Create or select the Exergi production Clerk application.
2. Add `https://exergi.vercel.app` as the production application origin and keep
   `http://localhost:3000` for local development only.
3. Record the publishable key and secret key directly in the Vercel environment UI.
4. Record the Clerk issuer/Frontend API URL and its `/.well-known/jwks.json` URL directly in
   Render. Do not create a custom JWT template unless an audience is deliberately required.

## 2. Render environment (manual)

Enter these in the `exergi-api` service Environment page:

- `EXERGI_DASHBOARD_URL=https://exergi.vercel.app`
- `CLERK_ISSUER_URL` from Clerk
- `CLERK_JWKS_URL` from Clerk
- `CLERK_AUTHORIZED_PARTIES=https://exergi.vercel.app`
- `CLERK_AUDIENCE` only if the Clerk token is configured with that exact audience

Keep the existing Shopify, database and encryption variables. Generate
`TENANT_PROVISIONING_KEY` as a new independent random value of at least 32 bytes. Do not reuse
the OAuth-state, token-encryption, pseudonym or former session-signing keys.

## 3. Vercel environment (manual)

Enter these for Production (and separately for Preview only if previews are intentionally used):

- `NEXT_PUBLIC_CLERK_PUBLISHABLE_KEY`
- `CLERK_SECRET_KEY`
- `NEXT_PUBLIC_EXERGI_API_URL=https://exergi-api.onrender.com`

Only the publishable Clerk key and public API URL use `NEXT_PUBLIC_`. Deployment Protection must
allow public access to the production domain; Clerk protects merchant routes inside the app.

## 4. Shopify app version (manual)

The App URL and callback remain:

- `https://exergi-api.onrender.com/api/v1/shopify/install`
- `https://exergi-api.onrender.com/api/v1/shopify/oauth/callback`

Keep embedded OFF, API version `2026-07`, and only the five read scopes in `shopify.app.toml`.
Before claiming webhook coverage, create/deploy an app version containing every subscription in
that file and confirm it is the active version in the Partner Dashboard. The webhook endpoint is
`https://exergi-api.onrender.com/api/v1/shopify/webhooks`.

## 5. Deployment order

1. Push the reviewed commits only after explicit approval.
2. Deploy Render and confirm `GET https://exergi-api.onrender.com/healthz` returns `{"status":"ok"}`.
3. Deploy Vercel and confirm the public home page loads while `/onboarding` redirects to Clerk.
4. Confirm `GET /api/v1/shopify/install?shop=<development-store>.myshopify.com` redirects to the
   same protected onboarding URL and does not start OAuth.

## 6. One live development-store test

1. Sign in to Exergi and open `/onboarding?shop=<development-store>.myshopify.com`.
2. Review the five read scopes, then press **Connect Shopify** once.
3. Approve the app in the Shopify development store.
4. Confirm the callback returns to onboarding and the UI reports `CONNECTED`/`SYNCING`, not ready.
5. Confirm Render has one tenant binding, one connected installation and one queued initial sync.
6. Reconcile source counts/totals and data-health before describing the store as data-ready.
7. Repeat the callback URL and verify nonce replay is rejected and no second sync is queued.
