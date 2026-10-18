# Skillet — Digital Cookbook

Skillet is a small, opinionated cookbook for shared meal planning. Recipe pages, week plans, QR-code guest voting, grocery aggregation with pantry exclusion, and honest retailer integrations. Built with Next.js 16, TypeScript, Tailwind v4, and Supabase (Postgres, Auth, Storage).

## Features

- **Cookbooks & members** — create private/public cookbooks, invite members as editors/viewers with expiring links (copy + QR), change roles, revoke invites, remove members. New signups get a profile and a default cookbook auto-created by a DB trigger.
- **Recipes** — manual creation or one-URL import; photos upload directly to Supabase Storage (`recipe-photos`, 5 MB image limit, path-scoped RLS); ingredient list scales with servings; tags, prep/cook times, source links.
- **Recipe import** — SSRF-safe fetcher (private-IP/localhost blocking, 5 MB cap, 5 redirects, 12 s timeout) plus JSON-LD → microdata → meta-tag parsing. Returns an editable draft or a 422 with a clear error.
- **Week plans & voting** — build a ballot per week, close/reopen voting, auto-pick top-voted recipes. Guests vote without accounts via invite link or QR: stable `guest:*` voter key in localStorage, name entry, 👍/👎 tallies, all enforced by SECURITY DEFINER RPCs (`get_vote_ballot`, `cast_vote`).
- **Grocery lists** — client-agnostic aggregation merges compatible units across selected recipes, formats quantities, tracks recipe provenance, and preserves checked/excluded state across rebuilds. Pantry staples are flagged and skipped by default.
- **Pantry** — personal pantry of staples managed on the `/settings` page; normalized names exclude matching items from every grocery build.
- **Shopping** — `/grocery/[planId]/shop` matches list items to Walmart/Instacart products with fuzzy-match confidence scores. Unconfigured retailers return real search links — never a simulated cart.
- **Guarded routes** — `src/proxy.ts` redirects unauthenticated users on `/cookbooks`, `/recipes`, `/import`, `/plans`, `/grocery`, `/settings` to `/login?next=…`, and bounces signed-in users away from `/login`/`/signup`.

### Route map

| Route | Purpose |
|---|---|
| `/`, `/login`, `/signup` | Landing + email/password auth |
| `/cookbooks`, `/cookbooks/[id]` | Cookbook list & detail (recipes, plans, start-a-week) |
| `/cookbooks/[id]/members` | Invites, roles, member removal |
| `/recipes/new`, `/recipes/[id]`, `/recipes/[id]/edit` | Recipe CRUD with photo upload & serving scaling |
| `/import` | Import a recipe from a URL |
| `/plans`, `/plans/[id]` | Vote plans: ballot editing, tallies, QR share, grocery build |
| `/invite/[token]`, `/vote/[token]` | Accept a member invite / guest voting (public) |
| `/grocery/[planId]`, `/grocery/[planId]/shop` | Grocery list + retailer shopping |
| `/settings` | Display name & pantry staples |
| `/api/import`, `/api/retailers`, `/api/shop` | Parse recipes, retailer status, cart/search |

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
node scripts/smoke.mjs  # HTTP smoke test against a production build
```

Notes:
- No `next lint` (run `eslint .` directly).
- Uses Next 16.4.2 conventions: `params`/`searchParams`/`cookies()` are Promises; middleware lives in `src/proxy.ts`.
- Pages with auth requirements redirect to `/login` when signed out (`src/proxy.ts`), preserving the original path as `?next=`.
- The smoke script boots `next start` on port 3210 (override with `SMOKE_PORT`) and checks the public surface: landing/login/signup load, `/vote/[token]` renders, protected routes redirect, `/api/retailers` reports honest config state, `/api/import` and `/api/shop` require auth, unknown routes 404.

## Testing strategy

- **Unit tests (Vitest)** cover ingredient parsing/normalization, grocery aggregation/merging, HTML import parsing, and retailer adapters (`tests/ingredients.test.ts`, `tests/grocery.test.ts`, `tests/import.test.ts`, `tests/retailers.test.ts`).
- **Migration + RLS tests** run the real Supabase migration against in-memory Postgres via `@electric-sql/pglite` with minimal `auth`/`storage` shims (`tests/migration.test.ts`, `tests/flow.test.ts`). Schema, triggers, `cookbook_role`/`can_view_cookbook`, `handle_new_user` auto-provisioning, invite/join, and vote RPCs are all exercised.
- **Live smoke tests** hit real recipe sites and verify SSRF guards (`tests/live.test.ts`) — skipped in CI by default (`SKIP_LIVE=1`).
- **HTTP smoke test** (`scripts/smoke.mjs`) boots the production server and probes routes/APIs end-to-end — run `npm run build` first.

## Deploy

1. Push the repo to GitHub/GitLab.
2. Create a Supabase project, run the migration in SQL Editor.
3. Deploy to Vercel (recommended). Set all required env vars from `.env.example`. If using a different host, set `NEXT_PUBLIC_APP_URL` to the public URL.
4. After deploy, sign up and create a cookbook. If env vars are missing, a SetupNotice renders instead of broken flows.

## Architecture highlights

- **Auth:** email+password via `@supabase/ssr`. Guests access vote pages via SECURITY DEFINER RPCs (`get_vote_ballot`, `cast_vote`) using anon key — no service role.
- **RBAC/RLS:** owners/editors/viewers enforced in SQL; server actions and queries reuse cookbook role checks (`cookbook_role`).
- **Auto-provisioning:** an `auth.users` trigger creates the profile and a default private cookbook on signup (`handle_new_user`).
- **Grocery:** client-agnostic aggregation in TypeScript merges compatible units, formats quantities, flags pantry staples. Stored in DB for manual tweaks; checked/excluded state survives rebuilds.
- **Pantry:** per-user staples with normalized names (`pantry_items`) exclude matching grocery items at build time; managed from `/settings`.
- **Retailers:** adapter pattern with honest behavior (never simulate cart IDs). Returns real product links when unconfigured; `/api/retailers` exposes a `configured` flag per retailer.
- **Import:** SSRF-safe fetcher (private-IP/localhost blocking, 5 MB cap, 5 redirects, 12 s timeout) + JSON-LD/microdata/metadata parsing; sanitizes to a strict schema.
- **Photos:** browser uploads straight to the `recipe-photos` bucket, keyed by cookbook ID so storage RLS can scope writes; 5 MB image limit.

## Project layout

```
src/
  app/            # routes, pages, server actions, API routes
  components/     # UI (recipe form/cards, voter, shop panel, QR, nav…)
  lib/            # auth, queries, ingredients, grocery/, import/, retailers/, supabase/
  proxy.ts        # middleware: session refresh + route guards
supabase/
  migrations/     # 20261017000001_init.sql (schema, RLS, RPCs, bucket)
tests/            # vitest suites + PGlite migration harness
scripts/smoke.mjs # production HTTP smoke test
```

## Automation (GitHub Actions)

`.github/workflows/Opencode.yml` runs [OpenCode](https://github.com/anomalyco/opencode) inside GitHub:

- **`issue_comment`** — any new issue comment is passed to OpenCode as the prompt, so you can ask for fixes/features by commenting on an issue.
- **`workflow_dispatch`** — manual runs with a free-form `prompt` input (defaults to "Analyze this repository").

The job checks out the repo, configures an `OpenCode` git identity, and runs `anomalyco/opencode/github@latest` with `contents`, `issues`, `pull-requests`, and `id-token` write permissions so it can commit, comment, and open PRs.

## Database schema (summary)

Single migration: `supabase/migrations/20261017000001_init.sql`.

| Area | Details |
|---|---|
| Tables | `profiles`, `cookbooks`, `cookbook_members`, `invites`, `weekly_plans`, `plan_recipes`, `votes`, `recipes`, `pantry_items`, `grocery_lists`, `grocery_items` |
| Roles | `owner` implicit; `editor`/`viewer` in `cookbook_members`; enforced by RLS |
| RPCs | `cookbook_role`, `can_view_cookbook`, `join_cookbook`, `get_vote_ballot`, `cast_vote`, `handle_new_user` (trigger) |
| Storage | public `recipe-photos` bucket; upload allowed only into a path prefixed with a cookbook you can edit |
| Guarantees | one grocery list per plan, one vote per (plan, recipe, voter), unique week per cookbook, updated_at triggers |

## Notes on credentials & honesty

We never fabricate a successful checkout. If a retailer integration can't create a cart (missing creds, API error, or endpoint not confirmed), the UI returns `status: 'error'` or `status: 'link'` with search URLs and the raw error message. Pantry exclusions and merged quantities are deterministic and test-covered.
