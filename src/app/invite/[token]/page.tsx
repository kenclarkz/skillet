import Link from 'next/link';
import { redirect } from 'next/navigation';
import { btnPrimary } from '@/components/ui';
import { requireUser } from '@/lib/auth';

export const dynamic = 'force-dynamic';

export default async function InvitePage({ params }: PageProps<'/invite/[token]'>) {
  const { token } = await params;
  const { supabase } = await requireUser();

  const { data, error } = await supabase.rpc('join_cookbook', { p_invite_token: token });

  if (error || !data) {
    return (
      <main className="mx-auto w-full max-w-md px-5 py-16 text-center">
        <h1 className="text-xl font-bold text-ink">This invite isn&apos;t valid</h1>
        <p className="mt-2 text-sm text-ink-soft">
          It may have expired, been revoked, or already used. Ask the owner for a new link.
        </p>
        <Link href="/cookbooks" className={`${btnPrimary} mt-5`}>
          Go to my cookbooks
        </Link>
      </main>
    );
  }

  redirect(`/cookbooks/${data as string}`);
}
