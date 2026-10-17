import Link from 'next/link';
import { ImportForm } from '@/components/import-form';
import { requireUser } from '@/lib/auth';
import { listCookbooks } from '@/lib/queries';

export const dynamic = 'force-dynamic';

export default async function ImportPage({ searchParams }: PageProps<'/import'>) {
  const { cookbook } = await searchParams;
  const { supabase, user } = await requireUser();

  const editable = (await listCookbooks(supabase, user.id)).filter(
    (book) => book.role === 'owner' || book.role === 'editor'
  );

  if (editable.length === 0) {
    return (
      <main className="mx-auto w-full max-w-2xl px-5 py-12 text-center">
        <h1 className="text-xl font-bold text-ink">Create a cookbook first</h1>
        <p className="mt-2 text-sm text-ink-soft">
          You need at least one cookbook you can edit before importing recipes.
        </p>
        <Link href="/cookbooks" className="mt-4 inline-block text-sm font-semibold text-terracotta">
          Go to cookbooks →
        </Link>
      </main>
    );
  }

  const requested = typeof cookbook === 'string' ? cookbook : undefined;
  const defaultCookbookId =
    requested && editable.some((b) => b.id === requested) ? requested : editable[0].id;

  return (
    <main className="mx-auto w-full max-w-3xl px-5 py-8">
      <h1 className="text-2xl font-bold tracking-tight text-ink">Import a recipe</h1>
      <p className="mt-1 text-sm text-ink-soft">
        Paste a link from a recipe website. We&apos;ll pull out the ingredients, times, servings, and steps
        into an editable draft — nothing is saved until you review it.
      </p>
      <div className="mt-6">
        <ImportForm
          cookbooks={editable.map((book) => ({ id: book.id, name: book.name }))}
          defaultCookbookId={defaultCookbookId}
        />
      </div>
    </main>
  );
}
