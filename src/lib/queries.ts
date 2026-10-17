import type { SupabaseClient } from '@supabase/supabase-js';
import type { Cookbook, CookbookMember, GroceryItem, Invite, PantryItem, PlanRecipe, Profile, Recipe, Vote, WeeklyPlan } from './types';

export interface CookbookSummary extends Cookbook {
  recipe_count: number;
  role: 'owner' | 'editor' | 'viewer';
}

export async function listCookbooks(
  supabase: SupabaseClient,
  userId: string
): Promise<CookbookSummary[]> {
  const [{ data: books, error }, { data: memberships }] = await Promise.all([
    supabase
      .from('cookbooks')
      .select('*, recipes(count)')
      .order('created_at', { ascending: true }),
    supabase.from('cookbook_members').select('cookbook_id, role').eq('user_id', userId),
  ]);
  if (error) throw new Error(error.message);

  const memberRoles = new Map<string, 'editor' | 'viewer'>(
    (memberships ?? []).map((m) => [m.cookbook_id as string, m.role as 'editor' | 'viewer'])
  );

  return (books ?? []).map((book) => {
    const raw = book as unknown as Cookbook & { recipes?: { count: number }[] };
    const count = raw.recipes?.[0]?.count ?? 0;
    const role: CookbookSummary['role'] =
      raw.owner_id === userId ? 'owner' : (memberRoles.get(raw.id) ?? 'viewer');
    return { ...raw, recipe_count: count, role };
  });
}

export async function getCookbook(
  supabase: SupabaseClient,
  id: string
): Promise<Cookbook | null> {
  const { data, error } = await supabase.from('cookbooks').select('*').eq('id', id).maybeSingle();
  if (error) throw new Error(error.message);
  return (data as Cookbook | null) ?? null;
}

export async function getRecipes(
  supabase: SupabaseClient,
  cookbookId: string
): Promise<Recipe[]> {
  const { data, error } = await supabase
    .from('recipes')
    .select('*')
    .eq('cookbook_id', cookbookId)
    .order('created_at', { ascending: false });
  if (error) throw new Error(error.message);
  return (data ?? []) as Recipe[];
}

export async function getRecipe(supabase: SupabaseClient, id: string): Promise<Recipe | null> {
  const { data, error } = await supabase.from('recipes').select('*').eq('id', id).maybeSingle();
  if (error) throw new Error(error.message);
  return (data as Recipe | null) ?? null;
}

export async function getPlans(supabase: SupabaseClient, cookbookId?: string): Promise<WeeklyPlan[]> {
  let query = supabase.from('weekly_plans').select('*').order('week_start', { ascending: false });
  if (cookbookId) query = query.eq('cookbook_id', cookbookId);
  const { data, error } = await query.limit(50);
  if (error) throw new Error(error.message);
  return (data ?? []) as WeeklyPlan[];
}

export async function getPlan(supabase: SupabaseClient, id: string): Promise<WeeklyPlan | null> {
  const { data, error } = await supabase.from('weekly_plans').select('*').eq('id', id).maybeSingle();
  if (error) throw new Error(error.message);
  return (data as WeeklyPlan | null) ?? null;
}

export async function getPlanRecipes(
  supabase: SupabaseClient,
  planId: string
): Promise<PlanRecipe[]> {
  const { data, error } = await supabase
    .from('plan_recipes')
    .select('plan_id, recipe_id, selected, recipes (*)')
    .eq('plan_id', planId);
  if (error) throw new Error(error.message);
  return (data ?? []).map((row) => ({
    plan_id: row.plan_id as string,
    recipe_id: row.recipe_id as string,
    selected: row.selected as boolean,
    recipe: (row as unknown as { recipes: Recipe | null }).recipes,
  }));
}

export async function getVotes(supabase: SupabaseClient, planId: string): Promise<Vote[]> {
  const { data, error } = await supabase.from('votes').select('*').eq('plan_id', planId);
  if (error) throw new Error(error.message);
  return (data ?? []) as Vote[];
}

export async function getMembers(
  supabase: SupabaseClient,
  cookbookId: string
): Promise<CookbookMember[]> {
  const { data, error } = await supabase
    .from('cookbook_members')
    .select('*')
    .eq('cookbook_id', cookbookId)
    .order('created_at', { ascending: true });
  if (error) throw new Error(error.message);
  const members = (data ?? []) as CookbookMember[];
  if (members.length > 0) {
    const { data: profiles } = await supabase
      .from('profiles')
      .select('*')
      .in('id', members.map((m) => m.user_id));
    const byId = new Map((profiles ?? []).map((p) => [(p as Profile).id, p as Profile]));
    for (const member of members) member.profile = byId.get(member.user_id) ?? null;
  }
  return members;
}

export async function getInvites(supabase: SupabaseClient, cookbookId: string): Promise<Invite[]> {
  const { data, error } = await supabase
    .from('invites')
    .select('*')
    .eq('cookbook_id', cookbookId)
    .order('created_at', { ascending: false });
  if (error) throw new Error(error.message);
  return (data ?? []) as Invite[];
}

export async function getGroceryListId(
  supabase: SupabaseClient,
  planId: string
): Promise<string | null> {
  const { data } = await supabase.from('grocery_lists').select('id').eq('plan_id', planId).maybeSingle();
  return (data?.id as string | undefined) ?? null;
}

export async function getGroceryItems(
  supabase: SupabaseClient,
  listId: string
): Promise<GroceryItem[]> {
  const { data, error } = await supabase
    .from('grocery_items')
    .select('*')
    .eq('list_id', listId)
    .order('in_pantry', { ascending: true })
    .order('sort_key', { ascending: true });
  if (error) throw new Error(error.message);
  return (data ?? []) as GroceryItem[];
}

export async function getPantry(supabase: SupabaseClient, userId: string): Promise<PantryItem[]> {
  const { data, error } = await supabase
    .from('pantry_items')
    .select('*')
    .eq('user_id', userId)
    .order('name', { ascending: true });
  if (error) throw new Error(error.message);
  return (data ?? []) as PantryItem[];
}

export async function getProfile(
  supabase: SupabaseClient,
  userId: string
): Promise<Profile | null> {
  const { data } = await supabase.from('profiles').select('*').eq('id', userId).maybeSingle();
  return (data as Profile | null) ?? null;
}
