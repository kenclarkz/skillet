'use server';

import { revalidatePath } from 'next/cache';
import { requireUser } from '@/lib/auth';
import { aggregateGroceries, type SourceIngredient } from '@/lib/grocery/aggregate';
import { normalizeIngredientName, parseIngredientLine } from '@/lib/ingredients';
import type { Ingredient } from '@/lib/types';

function toIngredients(value: unknown): Ingredient[] {
  if (!Array.isArray(value)) return [];
  return value.flatMap((raw) => {
    if (typeof raw === 'string') return [parseIngredientLine(raw)];
    if (raw && typeof raw === 'object') {
      const obj = raw as Record<string, unknown>;
      return [
        {
          qty: obj.qty != null ? String(obj.qty) : null,
          unit: obj.unit != null ? String(obj.unit) : null,
          name: String(obj.name ?? '').trim(),
          note: obj.note != null ? String(obj.note) : null,
        },
      ].filter((i) => i.name);
    }
    return [];
  });
}

export async function buildGroceryList(formData: FormData) {
  const { supabase, user } = await requireUser();
  const planId = String(formData.get('plan_id') ?? '');
  if (!planId) throw new Error('Missing plan.');

  const { data: plan, error: planError } = await supabase
    .from('weekly_plans')
    .select('id, cookbook_id')
    .eq('id', planId)
    .single();
  if (planError || !plan) throw new Error(planError?.message ?? 'Plan not found.');

  const { data: planRecipes, error: prError } = await supabase
    .from('plan_recipes')
    .select('recipe_id, selected, recipes (id, title, ingredients, servings)')
    .eq('plan_id', planId);
  if (prError) throw new Error(prError.message);

  // Winners: explicitly selected recipes. If none were selected, fall back to
  // the up-voted recipes; if there are no votes either, use the whole ballot.
  let chosen = (planRecipes ?? []).filter((row) => row.selected);

  if (chosen.length === 0) {
    const { data: votes } = await supabase
      .from('votes')
      .select('recipe_id, value')
      .eq('plan_id', planId);
    const totals = new Map<string, number>();
    for (const vote of votes ?? []) {
      totals.set(vote.recipe_id as string, (totals.get(vote.recipe_id as string) ?? 0) + Number(vote.value));
    }
    const winners = Array.from(totals.entries())
      .filter(([, score]) => score > 0)
      .sort((a, b) => b[1] - a[1])
      .map(([recipeId]) => recipeId);
    if (winners.length > 0) {
      chosen = (planRecipes ?? []).filter((row) => winners.includes(row.recipe_id));
    } else {
      chosen = planRecipes ?? [];
    }
  }

  const sourceIngredients: SourceIngredient[] = [];
  for (const row of chosen) {
    const recipe = (row as unknown as { recipes: { id: string; title: string; ingredients: unknown } | null })
      .recipes;
    if (!recipe) continue;
    for (const ing of toIngredients(recipe.ingredients)) {
      sourceIngredients.push({ ...ing, recipeId: recipe.id, recipeTitle: recipe.title });
    }
  }

  const { data: pantry } = await supabase
    .from('pantry_items')
    .select('normalized_name')
    .eq('user_id', user.id);
  const pantrySet = new Set((pantry ?? []).map((p) => p.normalized_name as string));

  const aggregated = aggregateGroceries(sourceIngredients, { pantry: pantrySet });

  const { data: existingList } = await supabase
    .from('grocery_lists')
    .select('id')
    .eq('plan_id', planId)
    .maybeSingle();

  let listId = existingList?.id as string | undefined;
  if (!listId) {
    const { data: created, error: createError } = await supabase
      .from('grocery_lists')
      .insert({ plan_id: planId, created_by: user.id })
      .select('id')
      .single();
    if (createError || !created) throw new Error(createError?.message ?? 'Could not create list.');
    listId = created.id;
  }

  // Preserve checked/excluded state for items that persist across rebuilds.
  const { data: existingItems } = await supabase
    .from('grocery_items')
    .select('normalized_name, unit, checked, excluded')
    .eq('list_id', listId);
  const stateByKey = new Map(
    (existingItems ?? []).map((item) => [
      `${item.normalized_name}|${item.unit ?? ''}`,
      { checked: item.checked as boolean, excluded: item.excluded as boolean },
    ])
  );

  await supabase.from('grocery_items').delete().eq('list_id', listId);

  if (aggregated.length > 0) {
    const rows = aggregated.map((item) => {
      const prior = stateByKey.get(`${item.normalized_name}|${item.unit}`);
      return {
        list_id: listId,
        name: item.name,
        normalized_name: item.normalized_name,
        qty: item.qty,
        unit: item.unit,
        recipe_ids: item.recipe_ids,
        in_pantry: item.in_pantry,
        excluded: item.in_pantry ? true : (prior?.excluded ?? false),
        checked: prior?.checked ?? false,
        sort_key: item.name.toLowerCase(),
      };
    });
    const { error: insertError } = await supabase.from('grocery_items').insert(rows);
    if (insertError) throw new Error(insertError.message);
  }

  revalidatePath(`/grocery/${planId}`);
  revalidatePath(`/plans/${planId}`);
}

export async function toggleGroceryItem(formData: FormData) {
  const { supabase } = await requireUser();
  const listId = String(formData.get('list_id') ?? '');
  const itemId = String(formData.get('item_id') ?? '');
  const field = String(formData.get('field') ?? 'checked');
  const value = formData.get('value') === 'true';
  const planId = String(formData.get('plan_id') ?? '');
  if (field !== 'checked' && field !== 'excluded') throw new Error('Invalid field.');

  const { error } = await supabase
    .from('grocery_items')
    .update({ [field]: value })
    .eq('id', itemId)
    .eq('list_id', listId);
  if (error) throw new Error(error.message);

  revalidatePath(`/grocery/${planId}`);
}

export async function addGroceryItem(formData: FormData) {
  const { supabase } = await requireUser();
  const listId = String(formData.get('list_id') ?? '');
  const planId = String(formData.get('plan_id') ?? '');
  const name = String(formData.get('name') ?? '').trim();
  const qtyRaw = String(formData.get('qty') ?? '').trim();
  const unit = String(formData.get('unit') ?? '').trim() || null;
  if (!listId || !name) throw new Error('Item name is required.');

  const qty = qtyRaw ? Number(qtyRaw) : null;

  const { error } = await supabase.from('grocery_items').insert({
    list_id: listId,
    name,
    normalized_name: normalizeIngredientName(name),
    qty: Number.isFinite(qty) ? qty : null,
    unit,
    sort_key: name.toLowerCase(),
  });
  if (error) throw new Error(error.message);

  revalidatePath(`/grocery/${planId}`);
}

export async function deleteGroceryItem(formData: FormData) {
  const { supabase } = await requireUser();
  const itemId = String(formData.get('item_id') ?? '');
  const planId = String(formData.get('plan_id') ?? '');

  const { error } = await supabase.from('grocery_items').delete().eq('id', itemId);
  if (error) throw new Error(error.message);

  revalidatePath(`/grocery/${planId}`);
}

/** Mark an item as a pantry staple for this user and remove it from the list. */
export async function markAsPantry(formData: FormData) {
  const { supabase, user } = await requireUser();
  const itemId = String(formData.get('item_id') ?? '');
  const planId = String(formData.get('plan_id') ?? '');
  const name = String(formData.get('name') ?? '').trim();
  if (!name) throw new Error('Missing item name.');

  const { error: pantryError } = await supabase
    .from('pantry_items')
    .upsert(
      { user_id: user.id, name, normalized_name: normalizeIngredientName(name) },
      { onConflict: 'user_id,normalized_name' }
    );
  if (pantryError) throw new Error(pantryError.message);

  const { error } = await supabase
    .from('grocery_items')
    .update({ in_pantry: true, excluded: true })
    .eq('id', itemId);
  if (error) throw new Error(error.message);

  revalidatePath(`/grocery/${planId}`);
  revalidatePath('/settings');
}
