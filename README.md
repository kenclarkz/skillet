# Skillet — Digital Cookbook

Skillet is a small, opinionated cookbook for shared meal planning. Recipe pages, week plans, QR-code guest voting, grocery aggregation with pantry exclusion, and honest retailer integrations. Built with Next.js 16, TypeScript, Tailwind v4, and Supabase (Postgres, Auth, Storage).

## Quick start (local)

1. **Install dependencies**
   ```bash
   npm i
   ```

2. **Create env file**
   ```bash
   cp .env.example .env.local
   ```
   Fill in:
   - `NEXT_PUBLIC_SUPABASE_URL` — your Supabase project URL
   - `NEXT_PUBLIC_SUPABASE_ANON_KEY` — your Supabase `anon` key
   - `NEXT_PUBLIC_APP_URL` — `http://localhost:3000` in dev

3. **Set up Supabase (no CLI required)**
   - Create a project at https://supabase.com
   - Open the SQL Editor and run `supabase/migrations/20261017000001_init.sql` (copy/paste or upload). 
   - In Storage → Buckets, ensure `recipe-photos` exists (migration creates it). If RLS blocks local file uploads, confirm storage policies.
   - Copy URL + anon key into `.env.local`.

4. **Run the app**
   ```bash
   npm run dev
   ```

## Environment variables

| Variable | Required | Notes |
|---|---|---|
| `NEXT_PUBLIC_SUPABASE_URL` | Yes | Supabase project URL |
| `NEXT_PUBLIC_SUPABASE_ANON_KEY` | Yes | Public anon key (safe for browser) |
| `NEXT_PUBLIC_APP_URL` | Yes | Absolute base URL for invites/QRs |
| `WALMART_CONSUMER_ID` | No | Enables live Walmart product search |
| `WALMART_PRIVATE_KEY` | No | Used for Walmart auth |
| `WALMART_ACCESS_TOKEN` | No | Optional Walmart access token |
| `WALMART_API_BASE` | No | Override Walmart API base |
| `WALMART_CART_ENDPOINT` | No | If set, attempts to create a real cart (otherwise search-only) |
| `INSTACART_API_KEY` | No | Enables live Instacart search/cart when using partner credentials |
| `INSTACART_API_BASE` | No | Override Instacart base |
| `INSTACART_SEARCH_PATH` | No | Override search path |
| `INSTACART_CART_PATH` | No | Override cart path |

> If retailer creds are missing, the app never fakes a cart. It shows the real error or real product search links. 

## Development commands

```bash
npm run dev        # start dev server (Turbopack)
npm run build      # production build
npm run start      # run production build
npm run lint       # eslint
npm run typecheck  # tsc --noEmit
npm run test       # unit + migration tests (in-memory PGlite)
npm run test:watch # watch mode
```

Notes:
- No `next lint` (run `eslint .` directly).
- Uses Next 16.4.2 conventions: `params`/`searchParams`/`cookies()` are Promises; middleware lives in `src/proxy.ts`.
- Pages with auth requirements redirect to `/login` when signed out.

## Testing strategy

- **Unit tests (Vitest)** cover ingredient parsing/normalization, grocery aggregation/merging, HTML import parsing, and retailer adapters (`tests/ingredients.test.ts`, `tests/grocery.test.ts`, `tests/import.test.ts`, `tests/retailers.test.ts`).
- **Migration + RLS tests** run the real Supabase migration against in-memory Postgres via `@electric-sql/pglite` with minimal `auth`/`storage` shims (`tests/migration.test.ts`, `tests/flow.test.ts`).
- **Live smoke tests** hit real recipe sites and verify SSRF guards (`tests/live.test.ts`) — skipped in CI by default (`SKIP_LIVE=1`).

## Deploy

1. Push the repo to GitHub/GitLab.
2. Create a Supabase project, run the migration in SQL Editor.
3. Deploy to Vercel (recommended). Set all required env vars from `.env.example`. If using a different host, set `NEXT_PUBLIC_APP_URL` to the public URL.
4. After deploy, sign up and create a cookbook. If env vars are missing, a SetupNotice renders instead of broken flows.

## Architecture highlights

- **Auth:** email+password via `@supabase/ssr`. Guests access vote pages via SECURITY DEFINER RPCs (`get_vote_ballot`, `cast_vote`) using anon key — no service role.
- **RBAC/RLS:** owners/editors/viewers enforced in SQL; server actions and queries reuse cookbook role checks.
- **Grocery:** client-agnostic aggregation in TypeScript merges compatible units, formats quantities, flags pantry staples. Stored in DB for manual tweaks.
- **Retailers:** adapter pattern with honest behavior (never simulate cart IDs). Returns real product links when unconfigured.
- **Import:** SSRF-safe fetcher + JSON-LD/microdata/metadata parsing; sanitizes to a strict schema.

## Notes on credentials & honesty

We never fabricate a successful checkout. If a retailer integration can't create a cart (missing creds, API error, or endpoint not confirmed), the UI returns `status: 'error'` or `status: 'link'` with search URLs and the raw error message. Pantry exclusions and merged quantities are deterministic and test-covered.
