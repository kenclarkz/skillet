'use client';

import { createBrowserClient } from '@supabase/ssr';
import { requireSupabaseEnv } from './env';

export function createClient() {
  const { url, anonKey } = requireSupabaseEnv();
  return createBrowserClient(url, anonKey);
}
