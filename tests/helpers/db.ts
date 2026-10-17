// PGlite test harness: runs the real Supabase migration against an in-memory
// Postgres, with minimal stand-ins for the `auth` and `storage` schemas that
// Supabase provides.

import { readFile } from 'node:fs/promises';
import path from 'node:path';
import { PGlite } from '@electric-sql/pglite';

export const MIGRATION_PATH = path.resolve(
  __dirname,
  '../../supabase/migrations/20261017000001_init.sql'
);

const SUPABASE_SHIM = `
create schema if not exists auth;
create schema if not exists storage;

do $$ begin
  create role anon nologin;
exception when duplicate_object then null; end $$;
do $$ begin
  create role authenticated nologin;
exception when duplicate_object then null; end $$;
do $$ begin
  create role service_role nologin;
exception when duplicate_object then null; end $$;

create table if not exists auth.users (
  id uuid primary key default gen_random_uuid(),
  email text,
  raw_user_meta_data jsonb not null default '{}'::jsonb
);

create or replace function auth.uid()
returns uuid language sql stable as $$
  select nullif(current_setting('request.jwt.claim.sub', true), '')::uuid
$$;

create table if not exists storage.buckets (
  id text primary key,
  name text not null,
  public boolean not null default false
);

create table if not exists storage.objects (
  id uuid primary key default gen_random_uuid(),
  bucket_id text not null,
  name text not null,
  owner uuid
);

create or replace function storage.foldername(name text)
returns text[] language sql immutable as $$
  select string_to_array(name, '/')
$$;
`;

const GRANTS = `
grant usage on schema public to anon, authenticated, service_role;
grant all on all tables in schema public to authenticated, service_role;
grant select on all tables in schema public to anon;
grant all on all sequences in schema public to authenticated, service_role;
grant usage on schema auth to anon, authenticated;
grant usage on schema storage to anon, authenticated;
grant all on storage.objects to authenticated;
grant all on storage.buckets to authenticated;
`;

export async function createTestDb(): Promise<PGlite> {
  const migration = await readFile(MIGRATION_PATH, 'utf8');
  const db = new PGlite();
  await db.exec(SUPABASE_SHIM);
  await db.exec(migration);
  await db.exec(GRANTS);
  return db;
}

/** Run a callback as a given authenticated user (enforces RLS). */
export async function asUser<T>(
  db: PGlite,
  userId: string | null,
  fn: () => Promise<T>
): Promise<T> {
  await db.exec(`set role authenticated;`);
  await db.query(`select set_config('request.jwt.claim.sub', $1, false)`, [userId ?? '']);
  try {
    return await fn();
  } finally {
    await db.exec(`reset role;`);
  }
}

/** Run a callback as the anonymous role (guests). */
export async function asAnon<T>(db: PGlite, fn: () => Promise<T>): Promise<T> {
  await db.exec(`set role anon;`);
  await db.query(`select set_config('request.jwt.claim.sub', '', false)`);
  try {
    return await fn();
  } finally {
    await db.exec(`reset role;`);
  }
}

/** Create an auth user (triggers profile + default cookbook). */
export async function createUser(
  db: PGlite,
  email: string,
  displayName: string
): Promise<string> {
  const res = await db.query<{ id: string }>(
    `insert into auth.users (email, raw_user_meta_data)
     values ($1, jsonb_build_object('display_name', $2::text))
     returning id`,
    [email, displayName]
  );
  return res.rows[0].id;
}
