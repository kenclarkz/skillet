import Link from 'next/link';
import { createCookbook } from '@/app/actions/cookbooks';
import { SubmitButton } from '@/components/submit-button';
import { Badge, Card, EmptyState, btnGhost, btnPrimary, inputBase, labelBase } from '@/components/ui';
import { requireUser } from '@/lib/auth';
import { listCookbooks } from '@/lib/queries';

export const dynamic = 'force-dynamic';

const roleTone = {
  owner: 'terracotta',
  editor: 'olive',
  viewer: 'neutral',
} as const;

export default async function CookbooksPage() {
  const { supabase, user } = await requireUser();
  const cookbooks = await listCookbooks(supabase, user.id);

  return (
    <main className="mx-auto w-full max-w-6xl px-5 py-8">
      <div className="flex flex-wrap items-end justify-between gap-3">
        <div>
          <h1 className="text-2xl font-bold tracking-tight text-ink sm:text-3xl">Your cookbooks</h1>
          <p className="mt-1 text-sm text-ink-soft">
            Private by default. Invite family to view or edit any cookbook.
          </p>
        </div>
      </div>

      <div className="mt-6 grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
        {cookbooks.map((book) => (
          <Link key={book.id} href={`/cookbooks/${book.id}`} className="group">
            <Card className="h-full transition group-hover:-translate-y-0.5 group-hover:shadow-md">
              <div className="flex items-start justify-between gap-2">
                <h2 className="text-lg font-semibold text-ink">{book.name}</h2>
                <Badge tone={roleTone[book.role]}>{book.role}</Badge>
              </div>
              {book.description ? (
                <p className="mt-1 line-clamp-2 text-sm text-ink-soft">{book.description}</p>
              ) : null}
              <p className="mt-4 text-sm font-medium text-terracotta-dark">
                {book.recipe_count} recipe{book.recipe_count === 1 ? '' : 's'}
              </p>
              <p className="mt-1 text-xs text-ink-soft">
                {book.is_private ? 'Private' : 'Shared publicly'}
              </p>
            </Card>
          </Link>
        ))}
      </div>

      {cookbooks.length === 0 ? (
        <div className="mt-6">
          <EmptyState
            title="No cookbooks yet"
            description="Create your first cookbook below to start collecting recipes."
          />
        </div>
      ) : null}

      <details className="mt-8 rounded-2xl border border-sand-dark/70 bg-white p-5">
        <summary className="cursor-pointer text-base font-semibold text-ink">
          + New cookbook
        </summary>
        <form action={createCookbook} className="mt-4 space-y-4">
          <div>
            <label className={labelBase} htmlFor="name">
              Name
            </label>
            <input id="name" name="name" required className={inputBase} placeholder="Family Favorites" />
          </div>
          <div>
            <label className={labelBase} htmlFor="description">
              Description
            </label>
            <textarea
              id="description"
              name="description"
              rows={2}
              className={inputBase}
              placeholder="Weeknight dinners we all agree on"
            />
          </div>
          <label className="flex items-center gap-2 text-sm text-ink-soft">
            <input type="checkbox" name="is_private" defaultChecked className="h-4 w-4 accent-[#c4532d]" />
            Keep this cookbook private
          </label>
          <SubmitButton pendingLabel="Creating…">Create cookbook</SubmitButton>
        </form>
      </details>

      <p className="mt-6 text-sm text-ink-soft">
        Looking for a recipe link? Use the{' '}
        <Link href="/import" className={btnGhost}>
          importer
        </Link>{' '}
        to paste a URL and turn it into an editable recipe.
      </p>
      <div className="mt-2">
        <Link href="/import" className={btnPrimary}>
          Import a recipe
        </Link>
      </div>
    </main>
  );
}
