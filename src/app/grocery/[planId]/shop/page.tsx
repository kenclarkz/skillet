import Link from 'next/link';
import { notFound } from 'next/navigation';
import { ShopPanel } from '@/components/shop-panel';
import { requireUser } from '@/lib/auth';
import { getGroceryItems, getGroceryListId, getPlan } from '@/lib/queries';
import { retailerStatus } from '@/lib/retailers';

export const dynamic = 'force-dynamic';

export default async function ShopPage({ params }: PageProps<'/grocery/[planId]/shop'>) {
  const { planId } = await params;
  const { supabase } = await requireUser();

  const plan = await getPlan(supabase, planId);
  if (!plan) notFound();

  const listId = await getGroceryListId(supabase, planId);
  const items = listId ? await getGroceryItems(supabase, listId) : [];
  const activeItems = items.filter((item) => !item.excluded);

  return (
    <main className="mx-auto w-full max-w-3xl px-5 py-8">
      <Link href={`/grocery/${planId}`} className="text-sm font-medium text-ink-soft hover:text-ink">
        ← Back to the list
      </Link>
      <h1 className="mt-1 text-2xl font-bold tracking-tight text-ink sm:text-3xl">Shop online</h1>
      <p className="mt-1 text-sm text-ink-soft">
        Match your list to products at a store. If direct integration isn&apos;t enabled, we&apos;ll
        give you real search links rather than a fake cart.
      </p>

      <div className="mt-6">
        <ShopPanel
          planId={planId}
          retailers={retailerStatus()}
          itemCount={activeItems.length}
        />
      </div>
    </main>
  );
}
