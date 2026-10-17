import Link from 'next/link';
import { notFound } from 'next/navigation';
import { createPlan } from '@/app/actions/plans';
import { updateCookbook, deleteCookbook } from '@/app/actions/cookbooks';
import { RecipeCard } from '@/components/recipe-card';
import { SubmitButton } from '@/components/submit-button';
import { Badge, Card, EmptyState, btnGhost, btnPrimary, btnSecondary, inputBase, labelBase } from '@/components/ui';
import { canEdit, getRole, requireUser } from '@/lib/auth';
import { getCookbook, getPlans, getRecipes } from '@/lib/queries';

export const dynamic = 'force-dynamic';

function formatWeek(weekStart: string): string {
  const date = new Date(`${weekStart}T12:00:00`);
  return `Week of ${date.toLocaleDateString(undefined, { month: 'short', day: 'numeric' })}`;
}

export default async function CookbookPage({ params }: PageProps<'/cookbooks/[id]'>) {
  const { id } = await params;
  const { supabase } = await requireUser();

  const cookbook = await getCookbook(supabase, id);
  if (!cookbook) notFound();

  const [recipes, plans, role] = await Promise.all([
    getRecipes(supabase, id),
    getPlans(supabase, id),
    getRole(supabase, id),
  ]);
  const editable = canEdit(role);

  const thisWeek = plans.find((plan) => plan.status === 'open') ?? plans[0];

  return (
    <main className="mx-auto w-full max-w-6xl px-5 py-8">
      <div className="flex flex-wrap items-start justify-between gap-4">
        <div className="min-w-0">
          <div className="flex flex-wrap items-center gap-2">
            <h1 className="text-2xl font-bold tracking-tight text-ink sm:text-3xl">{cookbook.name}</h1>
            <Badge tone={role === 'owner' ? 'terracotta' : role === 'editor' ? 'olive' : 'neutral'}>
              {role ?? 'viewer'}
            </Badge>
            {cookbook.is_private ? <Badge>private</Badge> : <Badge tone="honey">public</Badge>}
          </div>
          {cookbook.description ? (
            <p className="mt-2 max-w-2xl text-sm text-ink-soft">{cookbook.description}</p>
          ) : null}
        </div>

        <div className="flex flex-wrap gap-2">
          {editable ? (
            <>
              <Link href={`/import?cookbook=${cookbook.id}`} className={btnPrimary}>
                Import from URL
              </Link>
              <Link href={`/recipes/new?cookbook=${cookbook.id}`} className={btnSecondary}>
                Add manually
              </Link>
            </>
          ) : null}
          {role ? (
            <Link href={`/cookbooks/${cookbook.id}/members`} className={btnSecondary}>
              Members
            </Link>
          ) : null}
        </div>
      </div>

      <section className="mt-8">
        <div className="mb-3 flex items-end justify-between">
          <h2 className="text-lg font-semibold text-ink">Recipe cards</h2>
          <span className="text-sm text-ink-soft">{recipes.length} total</span>
        </div>

        {recipes.length === 0 ? (
          <EmptyState
            title="No recipes yet"
            description="Import a recipe from a URL or add one by hand. Photos make the cards pop."
            action={
              editable ? (
                <Link href={`/import?cookbook=${cookbook.id}`} className={btnPrimary}>
                  Import your first recipe
                </Link>
              ) : undefined
            }
          />
        ) : (
          <div className="no-scrollbar -mx-5 flex snap-x snap-mandatory gap-4 overflow-x-auto px-5 pb-4 sm:mx-0 sm:px-0">
            {recipes.map((recipe, index) => (
              <RecipeCard key={recipe.id} recipe={recipe} priority={index < 2} />
            ))}
          </div>
        )}
      </section>

      <section className="mt-10 grid gap-6 lg:grid-cols-[1.4fr_1fr]">
        <div>
          <h2 className="mb-3 text-lg font-semibold text-ink">Weekly meal votes</h2>
          {plans.length === 0 ? (
            <EmptyState
              title="No votes yet"
              description="Start a weekly plan, share the QR code, and let everyone weigh in."
            />
          ) : (
            <ul className="space-y-3">
              {plans.map((plan) => (
                <li key={plan.id}>
                  <Link href={`/plans/${plan.id}`} className="block">
                    <Card className="flex items-center justify-between gap-3 transition hover:shadow-md">
                      <div>
                        <p className="font-semibold text-ink">{plan.title ?? formatWeek(plan.week_start)}</p>
                        <p className="text-sm text-ink-soft">{formatWeek(plan.week_start)}</p>
                      </div>
                      <Badge tone={plan.status === 'open' ? 'olive' : 'neutral'}>{plan.status}</Badge>
                    </Card>
                  </Link>
                </li>
              ))}
            </ul>
          )}

          {editable ? (
            <form action={createPlan} className="mt-4 flex flex-wrap items-end gap-3">
              <input type="hidden" name="cookbook_id" value={cookbook.id} />
              <div>
                <label className={labelBase} htmlFor="week_start">
                  Week starting
                </label>
                <input id="week_start" name="week_start" type="date" className={inputBase} />
              </div>
              <SubmitButton pendingLabel="Starting…">Start a vote week</SubmitButton>
            </form>
          ) : null}
        </div>

        <div className="space-y-6">
          <Card>
            <h2 className="text-base font-semibold text-ink">Latest activity</h2>
            <p className="mt-1 text-sm text-ink-soft">
              {recipes.length} recipes · {plans.length} weekly votes
              {thisWeek ? ` · next up: ${thisWeek.title ?? formatWeek(thisWeek.week_start)}` : ''}
            </p>
            {thisWeek ? (
              <Link href={`/plans/${thisWeek.id}`} className={`${btnSecondary} mt-3 w-full`}>
                Open current vote
              </Link>
            ) : null}
          </Card>

          {role === 'owner' ? (
            <details className="rounded-2xl border border-sand-dark/70 bg-white p-5">
              <summary className="cursor-pointer text-base font-semibold text-ink">
                Cookbook settings
              </summary>
              <form action={updateCookbook} className="mt-4 space-y-3">
                <input type="hidden" name="id" value={cookbook.id} />
                <div>
                  <label className={labelBase} htmlFor="edit-name">
                    Name
                  </label>
                  <input id="edit-name" name="name" defaultValue={cookbook.name} className={inputBase} />
                </div>
                <div>
                  <label className={labelBase} htmlFor="edit-description">
                    Description
                  </label>
                  <textarea
                    id="edit-description"
                    name="description"
                    rows={2}
                    defaultValue={cookbook.description ?? ''}
                    className={inputBase}
                  />
                </div>
                <label className="flex items-center gap-2 text-sm text-ink-soft">
                  <input
                    type="checkbox"
                    name="is_private"
                    defaultChecked={cookbook.is_private}
                    className="h-4 w-4 accent-[#c4532d]"
                  />
                  Private cookbook
                </label>
                <SubmitButton variant="secondary">Save settings</SubmitButton>
              </form>

              <form action={deleteCookbook} className="mt-4 border-t border-sand-dark/60 pt-4">
                <input type="hidden" name="id" value={cookbook.id} />
                <SubmitButton variant="danger" pendingLabel="Deleting…">
                  Delete cookbook
                </SubmitButton>
              </form>
            </details>
          ) : (
            <Card>
              <p className="text-sm text-ink-soft">
                You have <strong>{role ?? 'viewer'}</strong> access.{' '}
                {editable ? 'You can add and edit recipes.' : 'Ask the owner for edit access to contribute.'}
              </p>
            </Card>
          )}

          <Link href={`/cookbooks/${cookbook.id}/members`} className={btnGhost}>
            Sharing &amp; permissions →
          </Link>
        </div>
      </section>
    </main>
  );
}
