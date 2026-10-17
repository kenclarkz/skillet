import Link from 'next/link';
import { btnPrimary, btnSecondary } from '@/components/ui';
import { isSupabaseConfigured } from '@/lib/supabase/env';
import { getCurrentUser } from '@/lib/supabase/server';

const FEATURES = [
  {
    icon: '📖',
    title: 'A visual cookbook',
    body: 'Swipe through recipe cards with big appetizing photos, then open any dish for full details.',
  },
  {
    icon: '🔗',
    title: 'Import from any URL',
    body: 'Paste a recipe link and we pull out ingredients, times, servings, and steps into an editable draft.',
  },
  {
    icon: '🗳️',
    title: 'Family votes by QR code',
    body: 'Share a QR link — grandma can vote on next week’s meals without creating an account.',
  },
  {
    icon: '🛒',
    title: 'Groceries that add up',
    body: 'Winning meals combine into one list with merged quantities, minus whatever is already in your pantry.',
  },
];

export default async function HomePage() {
  const configured = isSupabaseConfigured;
  const user = configured ? await getCurrentUser() : null;

  return (
    <main className="mx-auto w-full max-w-6xl px-5 pb-16 pt-10 sm:pt-16">
      <section className="grid items-center gap-10 lg:grid-cols-[1.1fr_0.9fr]">
        <div>
          <span className="inline-flex items-center gap-2 rounded-full bg-honey/15 px-3 py-1 text-xs font-semibold text-honey">
            For families who cook together
          </span>
          <h1 className="mt-4 text-4xl font-black leading-[1.05] tracking-tight text-ink sm:text-6xl">
            Every family recipe,
            <span className="text-terracotta"> one warm cookbook.</span>
          </h1>
          <p className="mt-4 max-w-xl text-base text-ink-soft sm:text-lg">
            Skillet keeps your dishes, photos, and notes in one private cookbook — then turns the
            meals you vote for into a ready-to-shop grocery list.
          </p>
          <div className="mt-7 flex flex-wrap gap-3">
            {user ? (
              <>
                <Link href="/cookbooks" className={btnPrimary}>
                  Open my cookbooks
                </Link>
                <Link href="/import" className={btnSecondary}>
                  Import a recipe
                </Link>
              </>
            ) : (
              <>
                <Link href="/signup" className={btnPrimary}>
                  Start your cookbook
                </Link>
                <Link href="/login" className={btnSecondary}>
                  I have an account
                </Link>
              </>
            )}
          </div>
          {!configured ? (
            <p className="mt-4 rounded-xl bg-terracotta/10 px-3 py-2 text-sm text-terracotta-dark">
              Supabase is not configured yet — see the setup steps on this page.
            </p>
          ) : null}
        </div>

        <div className="relative">
          <div className="no-scrollbar -mx-5 flex snap-x snap-mandatory gap-4 overflow-x-auto px-5 pb-4 lg:mx-0 lg:px-0">
            {[
              { emoji: '🌮', title: 'Taco night', sub: 'voted 5–1 for Friday' },
              { emoji: '🍝', title: 'Nonna’s ragù', sub: '3 hrs · serves 8' },
              { emoji: '🥗', title: 'Crunchy slaw', sub: 'pantry • 15 min' },
            ].map((card) => (
              <div
                key={card.title}
                className="w-56 shrink-0 snap-center overflow-hidden rounded-3xl border border-sand-dark bg-white shadow-sm"
              >
                <div className="flex h-36 items-center justify-center bg-gradient-to-br from-sand to-honey/30 text-5xl">
                  <span aria-hidden>{card.emoji}</span>
                </div>
                <div className="p-4">
                  <p className="font-semibold text-ink">{card.title}</p>
                  <p className="text-sm text-ink-soft">{card.sub}</p>
                </div>
              </div>
            ))}
          </div>
        </div>
      </section>

      <section className="mt-16 grid gap-4 sm:grid-cols-2">
        {FEATURES.map((feature) => (
          <div key={feature.title} className="rounded-2xl border border-sand-dark/70 bg-white p-5">
            <span className="text-2xl" aria-hidden>
              {feature.icon}
            </span>
            <h2 className="mt-2 text-base font-semibold text-ink">{feature.title}</h2>
            <p className="mt-1 text-sm text-ink-soft">{feature.body}</p>
          </div>
        ))}
      </section>
    </main>
  );
}
