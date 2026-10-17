'use server';

import { revalidatePath } from 'next/cache';
import { requireUser } from '@/lib/auth';
import { normalizeIngredientName } from '@/lib/ingredients';

export async function addPantryItem(formData: FormData) {
  const { supabase, user } = await requireUser();
  const name = String(formData.get('name') ?? '').trim();
  if (!name) throw new Error('Enter an item name.');

  const { error } = await supabase
    .from('pantry_items')
    .upsert(
      { user_id: user.id, name, normalized_name: normalizeIngredientName(name) },
      { onConflict: 'user_id,normalized_name' }
    );
  if (error) throw new Error(error.message);

  revalidatePath('/settings');
}

export async function removePantryItem(formData: FormData) {
  const { supabase, user } = await requireUser();
  const id = String(formData.get('id') ?? '');
  if (!id) throw new Error('Missing item.');

  const { error } = await supabase.from('pantry_items').delete().eq('id', id).eq('user_id', user.id);
  if (error) throw new Error(error.message);

  revalidatePath('/settings');
}

export async function updateProfileName(formData: FormData) {
  const { supabase, user } = await requireUser();
  const displayName = String(formData.get('display_name') ?? '').trim();
  if (!displayName) throw new Error('Enter your name.');

  const { error } = await supabase
    .from('profiles')
    .upsert({ id: user.id, display_name: displayName }, { onConflict: 'id' });
  if (error) throw new Error(error.message);

  revalidatePath('/settings');
}
