import Link from 'next/link';
import { redirect } from 'next/navigation';
import { RecipeForm } from '@/components/recipe-form';
import { requireUser } from '@/lib/auth';
import { listCookbooks } from '@/lib/queries';

export const dynamic = 'force-dynamic';

export default async function NewRecipePage({
  searchParams,
}: PageProps<'/recipes/new'>) {
  const { cookbook } = await searchParams;
  const { supabase, user } = await requireUser();

  const cookbooks = (await listCookbooks(supabase, user.id)).filter(
    (book) => book.role === 'owner' || book.role === 'editor'
  );

  if (cookbooks.length === 0) {
    return (
      <main className="mx-auto w-full max-w-2xl px-5 py-12 text-center">
        <h1 className="text-xl font-bold text-ink">No editable cookbook yet</h1>
        <p className="mt-2 text-sm text-ink-soft">
          Create a cookbook first, or ask an owner to grant you editor access.
        </p>
        <Link href="/cookbooks" className="mt-4 inline-block text-sm font-semibold text-terracotta">
          Go to cookbooks →
        </Link>
      </main>
    );
  }

  const requested = typeof cookbook === 'string' ? cookbook : undefined;
  const initial = requested && cookbooks.some((b) => b.id === requested) ? requested : cookbooks[0].id;
  if (requested && !cookbooks.some((b) => b.id === requested)) {
    redirect(`/recipes/new?cookbook=${initial}`);
  }

  return (
    <main className="mx-auto w-full max-w-3xl px-5 py-8">
      <h1 className="text-2xl font-bold tracking-tight text-ink">Add a recipe</h1>
      <p className="mt-1 text-sm text-ink-soft">
        Type it in, or paste a URL on the import page to fill this out automatically.
      </p>
      <div className="mt-6">
        <RecipeForm
          cookbookId={initial}
          cookbookOptions={cookbooks.map((book) => ({ id: book.id, name: book.name }))}
        />
      </div>
    </main>
  );
}
