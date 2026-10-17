import Link from 'next/link';
import { notFound } from 'next/navigation';
import {
  addRecipeToPlan,
  removeRecipeFromPlan,
  selectTopVoted,
  setPlanStatus,
  setRecipeSelected,
} from '@/app/actions/plans';
import { createInvite } from '@/app/actions/cookbooks';
import { buildGroceryList } from '@/app/actions/grocery';
import { CopyLink } from '@/components/copy-link';
import { QrCode } from '@/components/qr-code';
import { RecipePhoto } from '@/components/recipe-photo';
import { SubmitButton } from '@/components/submit-button';
import { Badge, Card, EmptyState, btnSecondary, inputBase, labelBase } from '@/components/ui';
import { canEdit, getRole, requireUser } from '@/lib/auth';
import { getCookbook, getInvites, getPlan, getPlanRecipes, getRecipes, getVotes } from '@/lib/queries';
import { publicPhotoUrl } from '@/lib/supabase/env';

export const dynamic = 'force-dynamic';

function appUrl(): string {
  return process.env.NEXT_PUBLIC_APP_URL?.replace(/\/$/, '') ?? '';
}

export default async function PlanPage({ params }: PageProps<'/plans/[id]'>) {
  const { id } = await params;
  const { supabase } = await requireUser();

  const plan = await getPlan(supabase, id);
  if (!plan) notFound();

  const [cookbook, role, planRecipes, votes, allRecipes, invites] = await Promise.all([
    getCookbook(supabase, plan.cookbook_id),
    getRole(supabase, plan.cookbook_id),
    getPlanRecipes(supabase, id),
    getVotes(supabase, id),
    getRecipes(supabase, plan.cookbook_id),
    getInvites(supabase, plan.cookbook_id),
  ]);
  if (!cookbook) notFound();

  const editable = canEdit(role);

  const tallies = new Map<string, { up: number; down: number; names: string[] }>();
  for (const vote of votes) {
    const entry = tallies.get(vote.recipe_id) ?? { up: 0, down: 0, names: [] };
    if (Number(vote.value) > 0) entry.up += 1;
    if (Number(vote.value) < 0) entry.down += 1;
    entry.names.push(vote.voter_name);
    tallies.set(vote.recipe_id, entry);
  }

  const activeVoteInvite = invites.find(
    (invite) =>
      invite.kind === 'vote' &&
      !invite.revoked_at &&
      (!invite.plan_id || invite.plan_id === plan.id) &&
      (!invite.expires_at || new Date(invite.expires_at) > new Date())
  );

  const ballotIds = new Set(planRecipes.map((row) => row.recipe_id));
  const addable = allRecipes.filter((recipe) => !ballotIds.has(recipe.id));
  const selectedCount = planRecipes.filter((row) => row.selected).length;

  return (
    <main className="mx-auto w-full max-w-5xl px-5 py-8">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <Link
            href={`/cookbooks/${cookbook.id}`}
            className="text-sm font-medium text-ink-soft hover:text-ink"
          >
            ← {cookbook.name}
          </Link>
          <h1 className="mt-1 text-2xl font-bold tracking-tight text-ink sm:text-3xl">
            {plan.title ?? `Week of ${plan.week_start}`}
          </h1>
          <div className="mt-2 flex items-center gap-2">
            <Badge tone={plan.status === 'open' ? 'olive' : 'neutral'}>{plan.status}</Badge>
            <span className="text-sm text-ink-soft">{plan.week_start}</span>
            {selectedCount > 0 ? (
              <Badge tone="terracotta">
                {selectedCount} on the menu
              </Badge>
            ) : null}
          </div>
        </div>

        <div className="flex flex-wrap gap-2">
          {editable ? (
            <>
              <form action={setPlanStatus}>
                <input type="hidden" name="plan_id" value={plan.id} />
                <input
                  type="hidden"
                  name="status"
                  value={plan.status === 'open' ? 'closed' : 'open'}
                />
                <SubmitButton variant="secondary" pendingLabel="…">
                  {plan.status === 'open' ? 'Close voting' : 'Reopen voting'}
                </SubmitButton>
              </form>
              <form action={selectTopVoted}>
                <input type="hidden" name="plan_id" value={plan.id} />
                <input type="hidden" name="slots" value={5} />
                <SubmitButton variant="secondary" pendingLabel="Tallying…">
                  Pick top 5 by votes
                </SubmitButton>
              </form>
              <form action={buildGroceryList}>
                <input type="hidden" name="plan_id" value={plan.id} />
                <SubmitButton pendingLabel="Building…">Build grocery list</SubmitButton>
              </form>
            </>
          ) : null}
        </div>
      </div>

      <section className="mt-8 grid gap-6 lg:grid-cols-[1fr_340px]">
        <div>
          <h2 className="mb-3 text-lg font-semibold text-ink">Ballot</h2>
          {planRecipes.length === 0 ? (
            <EmptyState
              title="Nothing to vote on yet"
              description="Add a few recipes below and share the invite link."
            />
          ) : (
            <ul className="space-y-3">
              {planRecipes
                .slice()
                .sort((a, b) => (tallies.get(b.recipe_id)?.up ?? 0) - (tallies.get(a.recipe_id)?.up ?? 0))
                .map((row) => {
                  const recipe = row.recipe;
                  if (!recipe) return null;
                  const tally = tallies.get(row.recipe_id) ?? { up: 0, down: 0, names: [] };
                  const photo = recipe.photo_url ?? publicPhotoUrl(recipe.photo_path);
                  return (
                    <li key={row.recipe_id}>
                      <Card className="flex gap-4 p-3">
                        <Link
                          href={`/recipes/${recipe.id}`}
                          className="relative h-20 w-20 shrink-0 overflow-hidden rounded-xl bg-sand"
                        >
                          <RecipePhoto src={photo} alt={recipe.title} sizes="80px" />
                        </Link>
                        <div className="min-w-0 flex-1">
                          <div className="flex flex-wrap items-center gap-2">
                            <Link href={`/recipes/${recipe.id}`} className="font-semibold text-ink">
                              {recipe.title}
                            </Link>
                            {row.selected ? <Badge tone="terracotta">on the menu</Badge> : null}
                          </div>
                          <p className="mt-1 text-sm text-ink-soft">
                            👍 {tally.up} · 👎 {tally.down}
                            {tally.names.length > 0 ? ` · ${tally.names.slice(0, 4).join(', ')}` : ''}
                          </p>
                          {editable ? (
                            <div className="mt-2 flex flex-wrap gap-2">
                              <form action={setRecipeSelected}>
                                <input type="hidden" name="plan_id" value={plan.id} />
                                <input type="hidden" name="recipe_id" value={recipe.id} />
                                <input type="hidden" name="selected" value={row.selected ? 'false' : 'true'} />
                                <SubmitButton variant="ghost" pendingLabel="…">
                                  {row.selected ? 'Remove from menu' : 'Add to menu'}
                                </SubmitButton>
                              </form>
                              <form action={removeRecipeFromPlan}>
                                <input type="hidden" name="plan_id" value={plan.id} />
                                <input type="hidden" name="recipe_id" value={recipe.id} />
                                <SubmitButton variant="ghost" pendingLabel="…">
                                  Remove
                                </SubmitButton>
                              </form>
                            </div>
                          ) : null}
                        </div>
                      </Card>
                    </li>
                  );
                })}
            </ul>
          )}

          {editable && addable.length > 0 ? (
            <form action={addRecipeToPlan} className="mt-4 flex flex-wrap items-end gap-3">
              <input type="hidden" name="plan_id" value={plan.id} />
              <div className="min-w-52 flex-1">
                <label className={labelBase} htmlFor="recipe_id">
                  Add a recipe to the ballot
                </label>
                <select id="recipe_id" name="recipe_id" className={inputBase}>
                  {addable.map((recipe) => (
                    <option key={recipe.id} value={recipe.id}>
                      {recipe.title}
                    </option>
                  ))}
                </select>
              </div>
              <SubmitButton variant="secondary" pendingLabel="Adding…">
                Add to ballot
              </SubmitButton>
            </form>
          ) : null}
        </div>

        <aside className="space-y-4">
          <Card>
            <h2 className="text-base font-semibold text-ink">Invite guests to vote</h2>
            <p className="mt-1 text-sm text-ink-soft">
              Family and friends can vote from their phones — no account needed.
            </p>

            {activeVoteInvite ? (
              <div className="mt-3 space-y-3">
                <CopyLink url={`${appUrl()}/vote/${activeVoteInvite.token}`} />
                <div className="flex justify-center">
                  <QrCode value={`${appUrl()}/vote/${activeVoteInvite.token}`} size={200} />
                </div>
                <p className="text-center text-xs text-ink-soft">Scan to vote</p>
              </div>
            ) : editable ? (
              <form action={createInvite} className="mt-3 space-y-3">
                <input type="hidden" name="cookbook_id" value={cookbook.id} />
                <input type="hidden" name="kind" value="vote" />
                <input type="hidden" name="plan_id" value={plan.id} />
                <div>
                  <label className={labelBase} htmlFor="expires_days">
                    Expires (days)
                  </label>
                  <input
                    id="expires_days"
                    name="expires_days"
                    type="number"
                    min={0}
                    defaultValue={14}
                    className={inputBase}
                  />
                </div>
                <SubmitButton pendingLabel="Creating…">Create vote link + QR</SubmitButton>
              </form>
            ) : (
              <p className="mt-3 text-sm text-ink-soft">Ask an editor to create the vote link.</p>
            )}
          </Card>

          <Card>
            <h2 className="text-base font-semibold text-ink">Grocery list</h2>
            <p className="mt-1 text-sm text-ink-soft">
              Combines ingredients from the meals on the menu, merges quantities, and skips your pantry
              staples.
            </p>
            <Link href={`/grocery/${plan.id}`} className={`${btnSecondary} mt-3 w-full`}>
              Open grocery list
            </Link>
          </Card>
        </aside>
      </section>
    </main>
  );
}
