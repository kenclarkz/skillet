'use client';

import Link from 'next/link';
import { useRouter, useSearchParams } from 'next/navigation';
import { useState } from 'react';
import { createClient } from '@/lib/supabase/client';
import { btnPrimary, inputBase, labelBase } from '@/components/ui';

export function AuthForm({ mode }: { mode: 'login' | 'signup' }) {
  const router = useRouter();
  const searchParams = useSearchParams();
  const nextPath = searchParams.get('next') ?? '/cookbooks';

  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [displayName, setDisplayName] = useState('');
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  async function onSubmit(event: React.FormEvent) {
    event.preventDefault();
    setError(null);
    setNotice(null);
    setBusy(true);
    try {
      const supabase = createClient();
      if (mode === 'signup') {
        const { data, error: signUpError } = await supabase.auth.signUp({
          email,
          password,
          options: {
            data: { display_name: displayName.trim() || email.split('@')[0] },
            emailRedirectTo: `${window.location.origin}/auth/callback?next=${encodeURIComponent(nextPath)}`,
          },
        });
        if (signUpError) throw signUpError;
        if (!data.session) {
          setNotice('Check your email to confirm your account, then sign in.');
          return;
        }
        router.push(nextPath);
        router.refresh();
        return;
      }

      const { error: signInError } = await supabase.auth.signInWithPassword({ email, password });
      if (signInError) throw signInError;
      router.push(nextPath);
      router.refresh();
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Something went wrong.');
    } finally {
      setBusy(false);
    }
  }

  return (
    <form onSubmit={onSubmit} className="space-y-4">
      {mode === 'signup' ? (
        <div>
          <label className={labelBase} htmlFor="displayName">
            Your name
          </label>
          <input
            id="displayName"
            className={inputBase}
            value={displayName}
            onChange={(e) => setDisplayName(e.target.value)}
            placeholder="Alex"
            autoComplete="name"
          />
        </div>
      ) : null}

      <div>
        <label className={labelBase} htmlFor="email">
          Email
        </label>
        <input
          id="email"
          type="email"
          required
          className={inputBase}
          value={email}
          onChange={(e) => setEmail(e.target.value)}
          placeholder="you@example.com"
          autoComplete="email"
        />
      </div>

      <div>
        <label className={labelBase} htmlFor="password">
          Password
        </label>
        <input
          id="password"
          type="password"
          required
          minLength={6}
          className={inputBase}
          value={password}
          onChange={(e) => setPassword(e.target.value)}
          placeholder="At least 6 characters"
          autoComplete={mode === 'signup' ? 'new-password' : 'current-password'}
        />
      </div>

      {error ? (
        <p className="rounded-xl bg-terracotta/10 px-3 py-2 text-sm text-terracotta-dark">{error}</p>
      ) : null}
      {notice ? (
        <p className="rounded-xl bg-olive/10 px-3 py-2 text-sm text-olive-dark">{notice}</p>
      ) : null}

      <button type="submit" disabled={busy} className={`${btnPrimary} w-full`}>
        {busy ? 'One moment…' : mode === 'signup' ? 'Create account' : 'Sign in'}
      </button>

      <p className="text-center text-sm text-ink-soft">
        {mode === 'signup' ? (
          <>
            Already have an account?{' '}
            <Link href={`/login?next=${encodeURIComponent(nextPath)}`} className="font-semibold text-terracotta">
              Sign in
            </Link>
          </>
        ) : (
          <>
            New here?{' '}
            <Link href={`/signup?next=${encodeURIComponent(nextPath)}`} className="font-semibold text-terracotta">
              Create an account
            </Link>
          </>
        )}
      </p>
    </form>
  );
}
