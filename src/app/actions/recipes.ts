'use server';

import { revalidatePath } from 'next/cache';
import { redirect } from 'next/navigation';
import { requireUser } from '@/lib/auth';
import { parseIngredientText } from '@/lib/ingredients';

function intOrNull(value: FormDataEntryValue | null): number | null {
  const str = String(value ?? '').trim();
  if (!str) return null;
  const n = parseInt(str, 10);
  return Number.isFinite(n) && n >= 0 ? n : null;
}

export async function saveRecipe(formData: FormData) {
  const { supabase, user } = await requireUser();

  const id = String(formData.get('id') ?? '').trim();
  const cookbookId = String(formData.get('cookbook_id') ?? '').trim();
  const title = String(formData.get('title') ?? '').trim();
  const description = String(formData.get('description') ?? '').trim() || null;
  const photoPath = String(formData.get('photo_path') ?? '').trim() || null;
  const sourceUrl = String(formData.get('source_url') ?? '').trim() || null;
  const prep = intOrNull(formData.get('prep_minutes'));
  const cook = intOrNull(formData.get('cook_minutes'));
  const servings = parseInt(String(formData.get('servings') ?? '4'), 10) || 4;
  const tags = String(formData.get('tags') ?? '')
    .split(',')
    .map((t) => t.trim())
    .filter(Boolean)
    .slice(0, 10);
  const ingredients = parseIngredientText(String(formData.get('ingredients_text') ?? ''));
  const instructions = String(formData.get('instructions_text') ?? '')
    .split('\n')
    .map((l) => l.trim().replace(/^\d+[.)]\s*/, ''))
    .filter(Boolean);

  if (!title) throw new Error('Give the recipe a title.');
  if (ingredients.length === 0) throw new Error('Add at least one ingredient.');

  const payload = {
    title,
    description,
    photo_path: photoPath,
    source_url: sourceUrl,
    prep_minutes: prep,
    cook_minutes: cook,
    servings: Math.min(Math.max(servings, 1), 100),
    tags,
    ingredients,
    instructions,
  };

  if (id) {
    const { error } = await supabase.from('recipes').update(payload).eq('id', id);
    if (error) throw new Error(error.message);
    revalidatePath(`/recipes/${id}`);
    revalidatePath('/cookbooks');
    redirect(`/recipes/${id}`);
  }

  if (!cookbookId) throw new Error('Choose a cookbook.');

  const { data, error } = await supabase
    .from('recipes')
    .insert({ ...payload, cookbook_id: cookbookId, created_by: user.id })
    .select('id')
    .single();
  if (error) throw new Error(error.message);

  revalidatePath(`/cookbooks/${cookbookId}`);
  redirect(`/recipes/${data.id}`);
}

export async function deleteRecipe(formData: FormData) {
  const { supabase } = await requireUser();
  const id = String(formData.get('id') ?? '');
  const cookbookId = String(formData.get('cookbook_id') ?? '');
  if (!id) throw new Error('Missing recipe.');

  const { error } = await supabase.from('recipes').delete().eq('id', id);
  if (error) throw new Error(error.message);

  revalidatePath(`/cookbooks/${cookbookId}`);
  redirect(`/cookbooks/${cookbookId}`);
}
