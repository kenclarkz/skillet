'use server';

import { revalidatePath } from 'next/cache';
import { redirect } from 'next/navigation';
import { requireUser } from '@/lib/auth';

export async function createCookbook(formData: FormData) {
  const { supabase, user } = await requireUser();
  const name = String(formData.get('name') ?? '').trim();
  const description = String(formData.get('description') ?? '').trim() || null;
  const isPrivate = formData.get('is_private') === 'on' || formData.get('is_private') === 'true';

  if (!name) throw new Error('Cookbook name is required.');

  const { data, error } = await supabase
    .from('cookbooks')
    .insert({ owner_id: user.id, name, description, is_private: isPrivate })
    .select('id')
    .single();

  if (error) throw new Error(error.message);
  revalidatePath('/cookbooks');
  redirect(`/cookbooks/${data.id}`);
}

export async function updateCookbook(formData: FormData) {
  const { supabase } = await requireUser();
  const id = String(formData.get('id') ?? '');
  const name = String(formData.get('name') ?? '').trim();
  const description = String(formData.get('description') ?? '').trim() || null;
  const isPrivate = formData.get('is_private') === 'on' || formData.get('is_private') === 'true';

  if (!id || !name) throw new Error('Cookbook name is required.');

  const { error } = await supabase
    .from('cookbooks')
    .update({ name, description, is_private: isPrivate })
    .eq('id', id);
  if (error) throw new Error(error.message);

  revalidatePath(`/cookbooks/${id}`);
  revalidatePath('/cookbooks');
}

export async function deleteCookbook(formData: FormData) {
  const { supabase } = await requireUser();
  const id = String(formData.get('id') ?? '');
  if (!id) throw new Error('Missing cookbook.');

  const { error } = await supabase.from('cookbooks').delete().eq('id', id);
  if (error) throw new Error(error.message);

  revalidatePath('/cookbooks');
  redirect('/cookbooks');
}

export async function createInvite(formData: FormData) {
  const { supabase, user } = await requireUser();
  const cookbookId = String(formData.get('cookbook_id') ?? '');
  const kind = String(formData.get('kind') ?? 'member') as 'member' | 'vote';
  const role = kind === 'member' ? (String(formData.get('role') ?? 'viewer') as 'editor' | 'viewer') : null;
  const planId = String(formData.get('plan_id') ?? '') || null;
  const days = Number(formData.get('expires_days') ?? 0);

  const expiresAt = days > 0 ? new Date(Date.now() + days * 86_400_000).toISOString() : null;

  const { error } = await supabase.from('invites').insert({
    cookbook_id: cookbookId,
    kind,
    role,
    plan_id: kind === 'vote' ? planId : null,
    created_by: user.id,
    expires_at: expiresAt,
  });
  if (error) throw new Error(error.message);

  revalidatePath(`/cookbooks/${cookbookId}/members`);
  if (planId) revalidatePath(`/plans/${planId}`);
}

export async function revokeInvite(formData: FormData) {
  const { supabase } = await requireUser();
  const id = String(formData.get('id') ?? '');
  const cookbookId = String(formData.get('cookbook_id') ?? '');

  const { error } = await supabase
    .from('invites')
    .update({ revoked_at: new Date().toISOString() })
    .eq('id', id);
  if (error) throw new Error(error.message);

  revalidatePath(`/cookbooks/${cookbookId}/members`);
}

export async function updateMemberRole(formData: FormData) {
  const { supabase } = await requireUser();
  const cookbookId = String(formData.get('cookbook_id') ?? '');
  const userId = String(formData.get('user_id') ?? '');
  const role = String(formData.get('role') ?? 'viewer') as 'editor' | 'viewer';

  const { error } = await supabase
    .from('cookbook_members')
    .update({ role })
    .eq('cookbook_id', cookbookId)
    .eq('user_id', userId);
  if (error) throw new Error(error.message);

  revalidatePath(`/cookbooks/${cookbookId}/members`);
}

export async function removeMember(formData: FormData) {
  const { supabase } = await requireUser();
  const cookbookId = String(formData.get('cookbook_id') ?? '');
  const userId = String(formData.get('user_id') ?? '');

  const { error } = await supabase
    .from('cookbook_members')
    .delete()
    .eq('cookbook_id', cookbookId)
    .eq('user_id', userId);
  if (error) throw new Error(error.message);

  revalidatePath(`/cookbooks/${cookbookId}/members`);
}
