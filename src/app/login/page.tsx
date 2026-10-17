import { Suspense } from 'react';
import { AuthForm } from '@/components/auth-form';

export default function LoginPage() {
  return (
    <main className="mx-auto flex w-full max-w-md flex-col justify-center px-5 py-12">
      <div className="mb-6 text-center">
        <span className="text-4xl" aria-hidden>
          🍳
        </span>
        <h1 className="mt-2 text-2xl font-bold tracking-tight">Welcome back</h1>
        <p className="mt-1 text-sm text-ink-soft">Sign in to your family cookbook.</p>
      </div>
      <div className="rounded-2xl border border-sand-dark/70 bg-white p-6 shadow-sm">
        <Suspense fallback={<p className="text-sm text-ink-soft">Loading…</p>}>
          <AuthForm mode="login" />
        </Suspense>
      </div>
    </main>
  );
}
