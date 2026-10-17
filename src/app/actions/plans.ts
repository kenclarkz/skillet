'use server';

import { revalidatePath } from 'next/cache';
import { redirect } from 'next/navigation';
import { requireUser } from '@/lib/auth';

function nextMonday(): string {
  const now = new Date();
  const day = now.getDay();
  const delta = day === 1 ? 7 : (8 - day) % 7 || 7;
  const monday = new Date(now);
  monday.setDate(now.getDate() + delta);
  return monday.toISOString().slice(0, 10);
}

export async function createPlan(formData: FormData) {
  const { supabase, user } = await requireUser();
  const cookbookId = String(formData.get('cookbook_id') ?? '');
  const weekStart = String(formData.get('week_start') ?? '').trim() || nextMonday();
  const title = String(formData.get('title') ?? '').trim() || null;

  if (!cookbookId) throw new Error('Missing cookbook.');

  const { data, error } = await supabase
    .from('weekly_plans')
    .upsert(
      { cookbook_id: cookbookId, week_start: weekStart, title, created_by: user.id },
      { onConflict: 'cookbook_id,week_start' }
    )
    .select('id')
    .single();
  if (error) throw new Error(error.message);

  revalidatePath(`/cookbooks/${cookbookId}`);
  revalidatePath('/plans');
  redirect(`/plans/${data.id}`);
}

export async function deletePlan(formData: FormData) {
  const { supabase } = await requireUser();
  const id = String(formData.get('id') ?? '');
  const cookbookId = String(formData.get('cookbook_id') ?? '');
  const { error } = await supabase.from('weekly_plans').delete().eq('id', id);
  if (error) throw new Error(error.message);
  revalidatePath('/plans');
  redirect(`/cookbooks/${cookbookId}`);
}

export async function addRecipeToPlan(formData: FormData) {
  const { supabase, user } = await requireUser();
  const planId = String(formData.get('plan_id') ?? '');
  const recipeId = String(formData.get('recipe_id') ?? '');
  if (!planId || !recipeId) throw new Error('Missing recipe.');

  const { error } = await supabase
    .from('plan_recipes')
    .upsert({ plan_id: planId, recipe_id: recipeId, added_by: user.id }, { onConflict: 'plan_id,recipe_id' });
  if (error) throw new Error(error.message);

  revalidatePath(`/plans/${planId}`);
}

export async function removeRecipeFromPlan(formData: FormData) {
  const { supabase } = await requireUser();
  const planId = String(formData.get('plan_id') ?? '');
  const recipeId = String(formData.get('recipe_id') ?? '');

  const { error } = await supabase
    .from('plan_recipes')
    .delete()
    .eq('plan_id', planId)
    .eq('recipe_id', recipeId);
  if (error) throw new Error(error.message);

  revalidatePath(`/plans/${planId}`);
}

export async function setRecipeSelected(formData: FormData) {
  const { supabase } = await requireUser();
  const planId = String(formData.get('plan_id') ?? '');
  const recipeId = String(formData.get('recipe_id') ?? '');
  const selected = formData.get('selected') === 'true';

  const { error } = await supabase
    .from('plan_recipes')
    .update({ selected })
    .eq('plan_id', planId)
    .eq('recipe_id', recipeId);
  if (error) throw new Error(error.message);

  revalidatePath(`/plans/${planId}`);
}

/** Select the top up-voted recipes (up to `slots`, default 5) for the week. */
export async function selectTopVoted(formData: FormData) {
  const { supabase } = await requireUser();
  const planId = String(formData.get('plan_id') ?? '');
  const slots = Number(formData.get('slots') ?? 5) || 5;

  const { data: votes, error: voteError } = await supabase
    .from('votes')
    .select('recipe_id, value')
    .eq('plan_id', planId);
  if (voteError) throw new Error(voteError.message);

  const totals = new Map<string, number>();
  for (const vote of votes ?? []) {
    totals.set(vote.recipe_id as string, (totals.get(vote.recipe_id as string) ?? 0) + Number(vote.value));
  }
  const winners = Array.from(totals.entries())
    .filter(([, score]) => score > 0)
    .sort((a, b) => b[1] - a[1])
    .slice(0, slots)
    .map(([recipeId]) => recipeId);

  await supabase.from('plan_recipes').update({ selected: false }).eq('plan_id', planId);
  if (winners.length > 0) {
    const { error } = await supabase
      .from('plan_recipes')
      .update({ selected: true })
      .eq('plan_id', planId)
      .in('recipe_id', winners);
    if (error) throw new Error(error.message);
  }

  revalidatePath(`/plans/${planId}`);
}

export async function setPlanStatus(formData: FormData) {
  const { supabase } = await requireUser();
  const planId = String(formData.get('plan_id') ?? '');
  const status = String(formData.get('status') ?? 'open');

  const { error } = await supabase.from('weekly_plans').update({ status }).eq('id', planId);
  if (error) throw new Error(error.message);

  revalidatePath(`/plans/${planId}`);
}
