import { redirect } from 'next/navigation';
import type { SupabaseClient, User } from '@supabase/supabase-js';
import { createClient } from '@/lib/supabase/server';
import type { CookbookRole } from '@/lib/types';

/** Server-side auth guard for actions and protected pages. */
export async function requireUser(): Promise<{ supabase: SupabaseClient; user: User }> {
  const supabase = await createClient();
  const {
    data: { user },
  } = await supabase.auth.getUser();
  if (!user) redirect('/login');
  return { supabase, user };
}

export async function optionalUser(): Promise<{ supabase: SupabaseClient; user: User | null }> {
  const supabase = await createClient();
  const {
    data: { user },
  } = await supabase.auth.getUser();
  return { supabase, user };
}

/** Current user's role in a cookbook (owner/editor/viewer) or null. */
export async function getRole(
  supabase: SupabaseClient,
  cookbookId: string
): Promise<CookbookRole | null> {
  const { data, error } = await supabase.rpc('cookbook_role', { cookbook_id: cookbookId });
  if (error) return null;
  return (data as CookbookRole | null) ?? null;
}

export function canEdit(role: CookbookRole | null): boolean {
  return role === 'owner' || role === 'editor';
}
