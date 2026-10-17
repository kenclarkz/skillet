'use client';

import { useState } from 'react';
import { RecipeForm, type RecipeDraft } from './recipe-form';
import { btnPrimary, inputBase, labelBase } from './ui';

export function ImportForm({
  cookbooks,
  defaultCookbookId,
}: {
  cookbooks: { id: string; name: string }[];
  defaultCookbookId: string;
}) {
  const [url, setUrl] = useState('');
  const [cookbookId, setCookbookId] = useState(defaultCookbookId);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [draft, setDraft] = useState<RecipeDraft | null>(null);
  const [method, setMethod] = useState<string | undefined>(undefined);

  async function fetchRecipe(event: React.FormEvent) {
    event.preventDefault();
    setError(null);
    setBusy(true);
    try {
      const res = await fetch('/api/import', {
        method: 'POST',
        headers: { 'content-type': 'application/json' },
        body: JSON.stringify({ url }),
      });
      const json = (await res.json()) as { draft?: RecipeDraft & { method?: string }; error?: string };
      if (json.draft) {
        setDraft({ ...json.draft, photo_path: json.draft.photo_url ?? null });
        setMethod(json.draft.method);
      }
      if (!res.ok) {
        setError(json.error ?? 'Import failed.');
      }
    } catch {
      setError('Could not reach the importer. Check your connection and try again.');
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="space-y-8">
      <form onSubmit={fetchRecipe} className="space-y-4 rounded-2xl border border-sand-dark/70 bg-white p-5">
        <div>
          <label className={labelBase} htmlFor="import-cookbook">
            Add to cookbook
          </label>
          <select
            id="import-cookbook"
            className={inputBase}
            value={cookbookId}
            onChange={(e) => setCookbookId(e.target.value)}
          >
            {cookbooks.map((book) => (
              <option key={book.id} value={book.id}>
                {book.name}
              </option>
            ))}
          </select>
        </div>

        <div>
          <label className={labelBase} htmlFor="import-url">
            Recipe URL
          </label>
          <input
            id="import-url"
            type="url"
            required
            className={inputBase}
            value={url}
            onChange={(e) => setUrl(e.target.value)}
            placeholder="https://example.com/best-lasagna"
          />
          <p className="mt-1 text-xs text-ink-soft">
            Works with most recipe sites (JSON-LD structured data). You can always edit the draft before saving.
          </p>
        </div>

        {error ? (
          <p className="rounded-xl bg-terracotta/10 px-3 py-2 text-sm text-terracotta-dark">{error}</p>
        ) : null}

        <button type="submit" disabled={busy} className={btnPrimary}>
          {busy ? 'Fetching…' : 'Fetch recipe details'}
        </button>
      </form>

      {draft ? (
        <div>
          <h2 className="mb-3 text-lg font-semibold text-ink">Editable draft</h2>
          <RecipeForm
            key={`${cookbookId}-${draft.title ?? ''}-${method ?? ''}`}
            cookbookId={cookbookId}
            draft={draft}
            importMethod={method}
          />
        </div>
      ) : null}
    </div>
  );
}
