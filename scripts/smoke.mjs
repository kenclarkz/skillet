#!/usr/bin/env node
// HTTP smoke test: boots the production server and checks the public surface.
// Usage: node scripts/smoke.mjs   (build first: npm run build)

import { spawn } from 'node:child_process';

const PORT = process.env.SMOKE_PORT ?? '3210';
const BASE = `http://127.0.0.1:${PORT}`;

const env = {
  ...process.env,
  NEXT_PUBLIC_SUPABASE_URL: process.env.NEXT_PUBLIC_SUPABASE_URL || 'https://placeholder.supabase.co',
  NEXT_PUBLIC_SUPABASE_ANON_KEY: process.env.NEXT_PUBLIC_SUPABASE_ANON_KEY || 'placeholder-anon-key',
  NEXT_PUBLIC_APP_URL: process.env.NEXT_PUBLIC_APP_URL || BASE,
  PORT,
};

const server = spawn('npx', ['next', 'start', '-p', PORT], { env, stdio: ['ignore', 'pipe', 'pipe'] });
let serverOutput = '';
server.stdout.on('data', (d) => (serverOutput += d.toString()));
server.stderr.on('data', (d) => (serverOutput += d.toString()));

async function waitForServer(timeoutMs = 60_000) {
  const started = Date.now();
  while (Date.now() - started < timeoutMs) {
    try {
      const res = await fetch(`${BASE}/`, { redirect: 'manual' });
      if (res.status > 0) return;
    } catch {
      // not up yet
    }
    await new Promise((r) => setTimeout(r, 500));
  }
  throw new Error(`Server did not start in time.\n${serverOutput}`);
}

const results = [];
function check(name, condition, detail = '') {
  results.push({ name, ok: Boolean(condition), detail });
}

async function run() {
  await waitForServer();

  const home = await fetch(`${BASE}/`);
  const homeHtml = await home.text();
  check('GET / returns 200', home.status === 200, `status ${home.status}`);
  check('Landing page mentions Skillet', homeHtml.includes('Skillet'));

  const login = await fetch(`${BASE}/login`);
  const loginHtml = await login.text();
  check('GET /login returns 200', login.status === 200, `status ${login.status}`);
  check('Login form present', loginHtml.includes('Sign in'));

  const signup = await fetch(`${BASE}/signup`);
  check('GET /signup returns 200', signup.status === 200, `status ${signup.status}`);

  const vote = await fetch(`${BASE}/vote/does-not-exist`);
  check('GET /vote/[token] returns 200', vote.status === 200, `status ${vote.status}`);

  const protectedRoute = await fetch(`${BASE}/cookbooks`, { redirect: 'manual' });
  check(
    'GET /cookbooks redirects unauthenticated users',
    protectedRoute.status === 307 || protectedRoute.status === 302,
    `status ${protectedRoute.status}`
  );

  const retailers = await fetch(`${BASE}/api/retailers`);
  const retailersJson = await retailers.json();
  check('GET /api/retailers returns 200', retailers.status === 200);
  check(
    'Retailers report configuration state honestly',
    Array.isArray(retailersJson.retailers) &&
      retailersJson.retailers.length === 2 &&
      retailersJson.retailers.every((r) => typeof r.configured === 'boolean'),
    JSON.stringify(retailersJson)
  );
  check(
    'Unconfigured retailers are marked as such',
    retailersJson.retailers.every((r) => r.configured === false),
    JSON.stringify(retailersJson.retailers)
  );

  const importRes = await fetch(`${BASE}/api/import`, {
    method: 'POST',
    headers: { 'content-type': 'application/json' },
    body: JSON.stringify({ url: 'https://example.com' }),
  });
  check('POST /api/import requires auth', importRes.status === 401, `status ${importRes.status}`);

  const shopRes = await fetch(`${BASE}/api/shop`, {
    method: 'POST',
    headers: { 'content-type': 'application/json' },
    body: JSON.stringify({ retailer: 'walmart', planId: 'nope' }),
  });
  check('POST /api/shop requires auth', shopRes.status === 401, `status ${shopRes.status}`);

  const missing = await fetch(`${BASE}/definitely-not-a-page`);
  check('Unknown route returns 404', missing.status === 404, `status ${missing.status}`);
}

run()
  .catch((err) => {
    check('Smoke run completed', false, err.message);
  })
  .finally(() => {
    server.kill('SIGKILL');
    let failed = 0;
    for (const r of results) {
      if (r.ok) {
        console.log(`  ✓ ${r.name}`);
      } else {
        failed += 1;
        console.log(`  ✗ ${r.name} ${r.detail ? `— ${r.detail}` : ''}`);
      }
    }
    console.log(`\n${results.length - failed}/${results.length} smoke checks passed`);
    process.exit(failed === 0 ? 0 : 1);
  });
