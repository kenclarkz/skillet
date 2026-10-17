export function SetupNotice() {
  return (
    <main className="mx-auto flex w-full max-w-2xl flex-col gap-6 px-5 py-12">
      <div className="flex items-center gap-2">
        <span className="text-3xl" aria-hidden>
          🍳
        </span>
        <h1 className="text-2xl font-bold tracking-tight">Skillet is almost ready</h1>
      </div>

      <p className="text-ink-soft">
        The app is running, but it needs a Supabase project for authentication, Postgres, and photo
        storage. Add these environment variables and restart:
      </p>

      <pre className="overflow-x-auto rounded-2xl border border-sand-dark bg-white p-4 text-sm">
{`NEXT_PUBLIC_SUPABASE_URL=https://YOUR-PROJECT.supabase.co
NEXT_PUBLIC_SUPABASE_ANON_KEY=YOUR-ANON-KEY`}
      </pre>

      <ol className="list-decimal space-y-2 pl-5 text-sm text-ink-soft">
        <li>Create a project at supabase.com (free tier is fine).</li>
        <li>
          Open the SQL editor and run{' '}
          <code className="rounded bg-sand px-1.5 py-0.5">supabase/migrations/20261017000001_init.sql</code>
          .
        </li>
        <li>
          Copy the Project URL and anon (publishable) key from Project Settings → API into{' '}
          <code className="rounded bg-sand px-1.5 py-0.5">.env.local</code>.
        </li>
        <li>Restart <code className="rounded bg-sand px-1.5 py-0.5">npm run dev</code>.</li>
      </ol>

      <p className="text-sm text-ink-soft">
        Full instructions, including optional Instacart and Walmart credentials, are in{' '}
        <code className="rounded bg-sand px-1.5 py-0.5">README.md</code>.
      </p>
    </main>
  );
}
