import { notFound, redirect } from 'next/navigation';
import { RecipeForm } from '@/components/recipe-form';
import { canEdit, getRole, requireUser } from '@/lib/auth';
import { getRecipe } from '@/lib/queries';
import { publicPhotoUrl } from '@/lib/supabase/env';

export const dynamic = 'force-dynamic';

export default async function EditRecipePage({ params }: PageProps<'/recipes/[id]/edit'>) {
  const { id } = await params;
  const { supabase } = await requireUser();

  const recipe = await getRecipe(supabase, id);
  if (!recipe) notFound();

  const role = await getRole(supabase, recipe.cookbook_id);
  if (!canEdit(role)) redirect(`/recipes/${id}`);

  return (
    <main className="mx-auto w-full max-w-3xl px-5 py-8">
      <h1 className="text-2xl font-bold tracking-tight text-ink">Edit recipe</h1>
      <p className="mt-1 text-sm text-ink-soft">Update the details, then save your changes.</p>
      <div className="mt-6">
        <RecipeForm
          cookbookId={recipe.cookbook_id}
          recipe={{ ...recipe, photo_url: recipe.photo_url ?? publicPhotoUrl(recipe.photo_path) }}
        />
      </div>
    </main>
  );
}
