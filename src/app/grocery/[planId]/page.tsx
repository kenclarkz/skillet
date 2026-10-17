import Link from 'next/link';
import { notFound } from 'next/navigation';
import { buildGroceryList } from '@/app/actions/grocery';
import { GroceryEditor } from '@/components/grocery-editor';
import { SubmitButton } from '@/components/submit-button';
import { EmptyState, btnSecondary } from '@/components/ui';
import { canEdit, getRole, requireUser } from '@/lib/auth';
import { getGroceryItems, getGroceryListId, getPlan, getPlanRecipes, getRecipes } from '@/lib/queries';

export const dynamic = 'force-dynamic';

export default async function GroceryPage({ params }: PageProps<'/grocery/[planId]'>) {
  const { planId } = await params;
  const { supabase } = await requireUser();

  const plan = await getPlan(supabase, planId);
  if (!plan) notFound();

  const [role, listId, planRecipes, recipes] = await Promise.all([
    getRole(supabase, plan.cookbook_id),
    getGroceryListId(supabase, planId),
    getPlanRecipes(supabase, planId),
    getRecipes(supabase, plan.cookbook_id),
  ]);
  const editable = canEdit(role);
  const items = listId ? await getGroceryItems(supabase, listId) : [];

  const titleById = new Map(recipes.map((recipe) => [recipe.id, recipe.title]));
  const itemsWithRecipes = items.map((item) => ({
    ...item,
    recipes: item.recipe_ids.map((id) => ({ id, title: titleById.get(id) ?? 'Recipe' })),
  }));

  const winningCount = planRecipes.filter((row) => row.selected).length;

  return (
    <main className="mx-auto w-full max-w-3xl px-5 py-8">
      <div className="no-print">
        <Link href={`/plans/${plan.id}`} className="text-sm font-medium text-ink-soft hover:text-ink">
          ← Back to the vote
        </Link>
        <h1 className="mt-1 text-2xl font-bold tracking-tight text-ink sm:text-3xl">Grocery list</h1>
        <p className="mt-1 text-sm text-ink-soft">
          {winningCount > 0
            ? `Combining ingredients from ${winningCount} meal${winningCount === 1 ? '' : 's'} on the menu.`
            : 'Built from the recipes with the most up-votes.'}{' '}
          Pantry staples you already have are skipped.
        </p>
      </div>

      <div className="mt-6">
        {!listId || items.length === 0 ? (
          <EmptyState
            title="No list yet"
            description="Build the list from this week's winning meals. You can rebuild it any time you change the menu."
            action={
              editable ? (
                <form action={buildGroceryList}>
                  <input type="hidden" name="plan_id" value={plan.id} />
                  <SubmitButton pendingLabel="Building…">Build grocery list</SubmitButton>
                </form>
              ) : (
                <Link href={`/plans/${plan.id}`} className={btnSecondary}>
                  Back to the vote
                </Link>
              )
            }
          />
        ) : (
          <>
            {editable ? (
              <div className="mb-4 flex flex-wrap items-center justify-between gap-3 no-print">
                <p className="text-sm text-ink-soft">
                  Changed the menu? Rebuild to re-merge quantities.
                </p>
                <form action={buildGroceryList}>
                  <input type="hidden" name="plan_id" value={plan.id} />
                  <SubmitButton variant="secondary" pendingLabel="Rebuilding…">
                    Rebuild list
                  </SubmitButton>
                </form>
              </div>
            ) : null}
            <GroceryEditor listId={listId} planId={plan.id} items={itemsWithRecipes} />
          </>
        )}
      </div>
    </main>
  );
}
