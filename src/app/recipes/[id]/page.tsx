import Link from 'next/link';
import { notFound } from 'next/navigation';
import { deleteRecipe } from '@/app/actions/recipes';
import { RecipeIngredients } from '@/components/recipe-ingredients';
import { RecipePhoto } from '@/components/recipe-photo';
import { SubmitButton } from '@/components/submit-button';
import { Badge, btnGhost, btnSecondary } from '@/components/ui';
import { canEdit, getRole, requireUser } from '@/lib/auth';
import { parseIngredientLine } from '@/lib/ingredients';
import { getRecipe } from '@/lib/queries';
import { publicPhotoUrl } from '@/lib/supabase/env';
import type { Ingredient, Recipe } from '@/lib/types';

export const dynamic = 'force-dynamic';

function normalizeIngredients(recipe: Recipe): Ingredient[] {
  return (recipe.ingredients ?? []).flatMap((entry) => {
    if (typeof entry === 'string') return [parseIngredientLine(entry)];
    if (entry && typeof entry === 'object' && 'name' in entry) return [entry as Ingredient];
    return [];
  });
}

export default async function RecipePage({ params }: PageProps<'/recipes/[id]'>) {
  const { id } = await params;
  const { supabase } = await requireUser();

  const recipe = await getRecipe(supabase, id);
  if (!recipe) notFound();

  const role = await getRole(supabase, recipe.cookbook_id);
  const editable = canEdit(role);
  const ingredients = normalizeIngredients(recipe);
  const photo = recipe.photo_url ?? publicPhotoUrl(recipe.photo_path);

  return (
    <main className="mx-auto w-full max-w-4xl px-5 py-8">
      <div className="flex items-center justify-between gap-3 no-print">
        <Link
          href={`/cookbooks/${recipe.cookbook_id}`}
          className="text-sm font-medium text-ink-soft hover:text-ink"
        >
          ← Back to cookbook
        </Link>
        <div className="flex gap-2">
          {editable ? (
            <Link href={`/recipes/${recipe.id}/edit`} className={btnSecondary}>
              Edit
            </Link>
          ) : null}
        </div>
      </div>

      <article className="mt-4">
        <div className="relative h-64 w-full overflow-hidden rounded-3xl bg-sand sm:h-80">
          <RecipePhoto
            src={photo}
            alt={recipe.title}
            priority
            sizes="(max-width: 768px) 100vw, 800px"
            className="object-cover"
          />
        </div>

        <h1 className="mt-5 text-3xl font-black tracking-tight text-ink sm:text-4xl">
          {recipe.title}
        </h1>

        {recipe.description ? (
          <p className="mt-2 max-w-2xl text-base text-ink-soft">{recipe.description}</p>
        ) : null}

        <div className="mt-4 flex flex-wrap gap-2">
          {recipe.prep_minutes ? <Badge tone="neutral">Prep {recipe.prep_minutes} min</Badge> : null}
          {recipe.cook_minutes ? <Badge tone="neutral">Cook {recipe.cook_minutes} min</Badge> : null}
          <Badge tone="honey">Serves {recipe.servings}</Badge>
          {recipe.tags.map((tag) => (
            <Badge key={tag} tone="olive">
              {tag}
            </Badge>
          ))}
        </div>

        <div className="mt-8 grid gap-8 lg:grid-cols-[minmax(0,320px)_1fr]">
          <section>
            <h2 className="mb-3 text-lg font-semibold text-ink">Ingredients</h2>
            {ingredients.length === 0 ? (
              <p className="text-sm text-ink-soft">No ingredients recorded yet.</p>
            ) : (
              <RecipeIngredients ingredients={ingredients} baseServings={recipe.servings} />
            )}
          </section>

          <section>
            <h2 className="mb-3 text-lg font-semibold text-ink">Instructions</h2>
            {recipe.instructions.length === 0 ? (
              <p className="text-sm text-ink-soft">No steps recorded yet.</p>
            ) : (
              <ol className="space-y-4">
                {recipe.instructions.map((step, index) => (
                  <li key={index} className="flex gap-3">
                    <span className="flex h-7 w-7 shrink-0 items-center justify-center rounded-full bg-terracotta/10 text-sm font-bold text-terracotta-dark">
                      {index + 1}
                    </span>
                    <p className="text-ink">{step}</p>
                  </li>
                ))}
              </ol>
            )}
          </section>
        </div>

        <div className="mt-8 flex flex-wrap items-center gap-3 border-t border-sand-dark/60 pt-4 no-print">
          {recipe.source_url ? (
            <a
              href={recipe.source_url}
              target="_blank"
              rel="noreferrer noopener"
              className={btnGhost}
            >
              View original source ↗
            </a>
          ) : null}
          {editable ? (
            <details className="ml-auto">
              <summary className="cursor-pointer text-sm font-medium text-terracotta-dark">
                Delete recipe
              </summary>
              <form action={deleteRecipe} className="mt-2">
                <input type="hidden" name="id" value={recipe.id} />
                <input type="hidden" name="cookbook_id" value={recipe.cookbook_id} />
                <SubmitButton variant="danger" pendingLabel="Deleting…">
                  Yes, delete this recipe
                </SubmitButton>
              </form>
            </details>
          ) : null}
        </div>
      </article>
    </main>
  );
}
