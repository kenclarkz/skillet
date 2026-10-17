import { Voter } from '@/components/voter';

export const dynamic = 'force-dynamic';

export const metadata = {
  title: 'Vote on this week’s meals',
};

export default async function VotePage({ params }: PageProps<'/vote/[token]'>) {
  const { token } = await params;

  return (
    <main className="mx-auto w-full max-w-lg px-4 py-6">
      <div className="mb-5 flex items-center justify-center gap-2">
        <span className="text-xl" aria-hidden>
          🍳
        </span>
        <span className="text-base font-bold tracking-tight text-ink">Skillet</span>
      </div>
      <Voter token={token} />
    </main>
  );
}
