import Link from 'next/link';
import { Card, EmptyState, btnPrimary } from '@/components/ui';
import { Badge } from '@/components/ui';
import { requireUser } from '@/lib/auth';
import { getPlans, listCookbooks } from '@/lib/queries';

export const dynamic = 'force-dynamic';

export default async function PlansPage() {
  const { supabase, user } = await requireUser();
  const [plans, cookbooks] = await Promise.all([
    getPlans(supabase),
    listCookbooks(supabase, user.id),
  ]);
  const cookbookName = new Map(cookbooks.map((book) => [book.id, book.name]));

  return (
    <main className="mx-auto w-full max-w-4xl px-5 py-8">
      <h1 className="text-2xl font-bold tracking-tight text-ink">Weekly meal votes</h1>
      <p className="mt-1 text-sm text-ink-soft">
        Share a QR code, collect votes, then turn the winners into a grocery list.
      </p>

      <div className="mt-6 space-y-3">
        {plans.map((plan) => (
          <Link key={plan.id} href={`/plans/${plan.id}`} className="block">
            <Card className="flex flex-wrap items-center justify-between gap-3 transition hover:shadow-md">
              <div>
                <p className="font-semibold text-ink">
                  {plan.title ?? `Week of ${plan.week_start}`}
                </p>
                <p className="text-sm text-ink-soft">
                  {cookbookName.get(plan.cookbook_id) ?? 'Cookbook'} · {plan.week_start}
                </p>
              </div>
              <Badge tone={plan.status === 'open' ? 'olive' : 'neutral'}>{plan.status}</Badge>
            </Card>
          </Link>
        ))}
      </div>

      {plans.length === 0 ? (
        <div className="mt-6">
          <EmptyState
            title="No votes yet"
            description="Open a cookbook and start a vote week to invite everyone."
            action={
              <Link href="/cookbooks" className={btnPrimary}>
                Go to cookbooks
              </Link>
            }
          />
        </div>
      ) : null}
    </main>
  );
}
