import { addPantryItem, removePantryItem, updateProfileName } from '@/app/actions/pantry';
import { SubmitButton } from '@/components/submit-button';
import { Card, EmptyState, inputBase, labelBase } from '@/components/ui';
import { requireUser } from '@/lib/auth';
import { getPantry, getProfile } from '@/lib/queries';

export const dynamic = 'force-dynamic';

export default async function SettingsPage() {
  const { supabase, user } = await requireUser();
  const [profile, pantry] = await Promise.all([
    getProfile(supabase, user.id),
    getPantry(supabase, user.id),
  ]);

  return (
    <main className="mx-auto w-full max-w-3xl px-5 py-8">
      <h1 className="text-2xl font-bold tracking-tight text-ink sm:text-3xl">Pantry &amp; profile</h1>
      <p className="mt-1 text-sm text-ink-soft">
        Pantry staples are skipped automatically when grocery lists are built — salt, oil, spices, and
        anything else you always have at home.
      </p>

      <Card className="mt-6">
        <h2 className="text-base font-semibold text-ink">Your name</h2>
        <form action={updateProfileName} className="mt-3 flex flex-wrap items-end gap-3">
          <div className="min-w-52 flex-1">
            <label className={labelBase} htmlFor="display_name">
              Display name
            </label>
            <input
              id="display_name"
              name="display_name"
              defaultValue={profile?.display_name ?? ''}
              className={inputBase}
            />
          </div>
          <SubmitButton variant="secondary" pendingLabel="Saving…">
            Save
          </SubmitButton>
        </form>
        <p className="mt-2 text-xs text-ink-soft">Signed in as {user.email}</p>
      </Card>

      <Card className="mt-6">
        <h2 className="text-base font-semibold text-ink">Pantry staples ({pantry.length})</h2>

        <form action={addPantryItem} className="mt-3 flex flex-wrap items-end gap-3">
          <div className="min-w-52 flex-1">
            <label className={labelBase} htmlFor="pantry-name">
              Add a staple
            </label>
            <input
              id="pantry-name"
              name="name"
              required
              placeholder="Olive oil"
              className={inputBase}
            />
          </div>
          <SubmitButton variant="secondary" pendingLabel="Adding…">
            Add to pantry
          </SubmitButton>
        </form>

        <div className="mt-4">
          {pantry.length === 0 ? (
            <EmptyState
              title="Your pantry is empty"
              description="Add the basics you always keep on hand so they never show up on the shopping list."
            />
          ) : (
            <ul className="flex flex-wrap gap-2">
              {pantry.map((item) => (
                <li key={item.id}>
                  <form action={removePantryItem}>
                    <input type="hidden" name="id" value={item.id} />
                    <button
                      type="submit"
                      className="inline-flex items-center gap-2 rounded-full bg-sand px-3 py-1.5 text-sm text-ink-soft hover:bg-sand-dark"
                      title="Remove from pantry"
                    >
                      {item.name}
                      <span aria-hidden>×</span>
                    </button>
                  </form>
                </li>
              ))}
            </ul>
          )}
        </div>
      </Card>
    </main>
  );
}
