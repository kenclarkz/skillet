'use client';

import Link from 'next/link';
import { usePathname, useRouter } from 'next/navigation';
import { useState } from 'react';
import { createClient } from '@/lib/supabase/client';
import { cn } from './ui';

const LINKS = [
  { href: '/cookbooks', label: 'Cookbooks', icon: '📚' },
  { href: '/plans', label: 'Votes', icon: '🗳️' },
  { href: '/import', label: 'Import', icon: '🔗' },
  { href: '/settings', label: 'Pantry', icon: '🧂' },
];

const HIDDEN_PREFIXES = ['/login', '/signup', '/vote/', '/invite/', '/setup'];

export function AppNav({ displayName }: { displayName: string | null }) {
  const pathname = usePathname();
  const router = useRouter();
  const [busy, setBusy] = useState(false);

  if (HIDDEN_PREFIXES.some((p) => pathname.startsWith(p))) {
    return null;
  }

  async function signOut() {
    setBusy(true);
    try {
      const supabase = createClient();
      await supabase.auth.signOut();
      router.push('/login');
      router.refresh();
    } finally {
      setBusy(false);
    }
  }

  const isActive = (href: string) =>
    pathname === href || pathname.startsWith(`${href}/`) ||
    (href === '/cookbooks' && pathname.startsWith('/recipes'));

  return (
    <>
      <header className="sticky top-0 z-30 border-b border-sand-dark/60 bg-cream/90 backdrop-blur">
        <div className="mx-auto flex w-full max-w-6xl items-center justify-between gap-3 px-4 py-3">
          <Link href="/" className="flex items-center gap-2">
            <span className="text-xl" aria-hidden>
              🍳
            </span>
            <span className="text-lg font-bold tracking-tight text-ink">Skillet</span>
          </Link>

          <nav className="hidden items-center gap-1 sm:flex">
            {LINKS.map((link) => (
              <Link
                key={link.href}
                href={link.href}
                className={cn(
                  'rounded-full px-3.5 py-2 text-sm font-medium transition',
                  isActive(link.href)
                    ? 'bg-terracotta/10 text-terracotta-dark'
                    : 'text-ink-soft hover:bg-sand hover:text-ink'
                )}
              >
                {link.label}
              </Link>
            ))}
          </nav>

          <div className="flex items-center gap-2">
            <span className="hidden max-w-[10rem] truncate text-sm text-ink-soft md:block">
              {displayName}
            </span>
            <button onClick={signOut} disabled={busy} className="text-sm font-medium text-ink-soft hover:text-terracotta">
              {busy ? 'Signing out…' : 'Sign out'}
            </button>
          </div>
        </div>
      </header>

      <nav className="safe-bottom fixed inset-x-0 bottom-0 z-30 border-t border-sand-dark/70 bg-cream/95 backdrop-blur sm:hidden">
        <div className="mx-auto flex max-w-md items-stretch justify-around">
          {LINKS.map((link) => (
            <Link
              key={link.href}
              href={link.href}
              className={cn(
                'flex flex-1 flex-col items-center gap-0.5 px-2 py-2 text-[11px] font-medium transition',
                isActive(link.href) ? 'text-terracotta-dark' : 'text-ink-soft'
              )}
            >
              <span className="text-lg" aria-hidden>
                {link.icon}
              </span>
              {link.label}
            </Link>
          ))}
        </div>
      </nav>
    </>
  );
}
