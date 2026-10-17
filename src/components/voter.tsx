'use client';

import { useCallback, useEffect, useMemo, useState } from 'react';
import { createClient } from '@/lib/supabase/client';
import { RecipePhoto } from '@/components/recipe-photo';
import { inputBase, labelBase } from '@/components/ui';
import { publicPhotoUrl } from '@/lib/supabase/env';
import { GUEST_KEY_STORAGE, GUEST_NAME_STORAGE, generateVoterKey } from '@/lib/guest';

interface BallotRecipe {
  id: string;
  title: string;
  description: string | null;
  photo_path: string | null;
  tags: string[];
  prep_minutes: number | null;
  cook_minutes: number | null;
  servings: number;
}

interface Ballot {
  cookbook: { id: string; name: string } | null;
  plan: { id: string; week_start: string; title: string | null; status: string } | null;
  recipes: BallotRecipe[];
  tallies: Record<string, { up: number; down: number; names: string[] }>;
  my_votes: Record<string, number>;
}

const NAME_KEY = GUEST_NAME_STORAGE;

function guestKey(): string {
  if (typeof window === 'undefined') return 'guest:unknown';
  let key = window.localStorage.getItem(GUEST_KEY_STORAGE);
  if (!key) {
    key = generateVoterKey();
    window.localStorage.setItem(GUEST_KEY_STORAGE, key);
  }
  return key;
}

export function Voter({ token }: { token: string }) {
  const supabase = useMemo(() => createClient(), []);
  const [name, setName] = useState('');
  const [nameDraft, setNameDraft] = useState('');
  const [ballot, setBallot] = useState<Ballot | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [saving, setSaving] = useState<string | null>(null);

  const voteKey = useMemo(() => guestKey(), []);

  const load = useCallback(
    async (voterName: string) => {
      const { data, error: rpcError } = await supabase.rpc('get_vote_ballot', {
        p_invite_token: token,
        p_voter_key: voteKey,
      });
      if (rpcError) {
        setError(rpcError.message);
      } else {
        setBallot(data as Ballot);
      }
      setLoading(false);
      if (voterName) setName(voterName);
    },
    [supabase, token, voteKey]
  );

  useEffect(() => {
    let cancelled = false;
    void (async () => {
      const stored = window.localStorage.getItem(NAME_KEY) ?? '';
      if (cancelled) return;
      if (stored) setNameDraft(stored);
      await load(stored);
    })();
    return () => {
      cancelled = true;
    };
  }, [load]);

  async function castVote(recipeId: string, value: number) {
    if (!ballot?.plan) return;
    const voterName = name.trim() || nameDraft.trim();
    if (!voterName) {
      setError('Add your name before voting.');
      return;
    }
    if (voterName !== name) {
      setName(voterName);
      window.localStorage.setItem(NAME_KEY, voterName);
    }
    setSaving(recipeId);
    setError(null);

    const current = ballot.my_votes[recipeId] ?? 0;
    const next = current === value ? 0 : value;

    const { error: rpcError } = await supabase.rpc('cast_vote', {
      p_plan_id: ballot.plan.id,
      p_recipe_id: recipeId,
      p_voter_key: voteKey,
      p_voter_name: voterName,
      p_value: next,
      p_invite_token: token,
    });

    if (rpcError) {
      setError(rpcError.message);
    } else {
      await load(voterName);
    }
    setSaving(null);
  }

  if (loading) {
    return <p className="py-16 text-center text-sm text-ink-soft">Loading the ballot…</p>;
  }

  if (!ballot || !ballot.plan) {
    return (
      <div className="rounded-2xl border border-sand-dark bg-white p-6 text-center">
        <h1 className="text-lg font-semibold text-ink">This voting link is not available</h1>
        <p className="mt-2 text-sm text-ink-soft">
          It may have expired or been revoked. Ask whoever shared it for a fresh link.
        </p>
        {error ? <p className="mt-3 text-xs text-terracotta-dark">{error}</p> : null}
      </div>
    );
  }

  return (
    <div className="space-y-6">
      <div>
        <p className="text-xs font-semibold uppercase tracking-wide text-terracotta">
          {ballot.cookbook?.name ?? 'Cookbook'}
        </p>
        <h1 className="mt-1 text-2xl font-bold tracking-tight text-ink">
          {ballot.plan.title ?? `Vote for the week of ${ballot.plan.week_start}`}
        </h1>
        <p className="mt-1 text-sm text-ink-soft">
          Tap 👍 for dishes you want and 👎 for ones you don&apos;t. No account needed.
        </p>
      </div>

      <div className="rounded-2xl border border-sand-dark bg-white p-4">
        <label className={labelBase} htmlFor="voter-name">
          Your name
        </label>
        <input
          id="voter-name"
          className={inputBase}
          value={nameDraft}
          placeholder="Grandma"
          onChange={(e) => setNameDraft(e.target.value)}
          onBlur={() => {
            const value = nameDraft.trim();
            setName(value);
            if (value) window.localStorage.setItem(NAME_KEY, value);
          }}
        />
      </div>

      {error ? (
        <p className="rounded-xl bg-terracotta/10 px-3 py-2 text-sm text-terracotta-dark">{error}</p>
      ) : null}

      {ballot.recipes.length === 0 ? (
        <p className="rounded-2xl border border-dashed border-sand-dark bg-white/60 px-4 py-8 text-center text-sm text-ink-soft">
          No recipes have been added to this vote yet. Check back soon!
        </p>
      ) : (
        <ul className="space-y-4">
          {ballot.recipes.map((recipe) => {
            const tally = ballot.tallies[recipe.id] ?? { up: 0, down: 0, names: [] };
            const myVote = ballot.my_votes[recipe.id] ?? 0;
            const photo = publicPhotoUrl(recipe.photo_path);
            return (
              <li
                key={recipe.id}
                className="overflow-hidden rounded-2xl border border-sand-dark bg-white shadow-sm"
              >
                <div className="relative h-40 w-full bg-sand">
                  <RecipePhoto src={photo} alt={recipe.title} sizes="(max-width: 640px) 100vw, 480px" />
                </div>
                <div className="p-4">
                  <h2 className="text-lg font-semibold text-ink">{recipe.title}</h2>
                  {recipe.description ? (
                    <p className="mt-1 line-clamp-2 text-sm text-ink-soft">{recipe.description}</p>
                  ) : null}
                  <div className="mt-3 flex items-center gap-3">
                    <button
                      type="button"
                      onClick={() => castVote(recipe.id, 1)}
                      disabled={saving === recipe.id}
                      className={`flex-1 rounded-full border px-4 py-3 text-sm font-semibold transition ${
                        myVote === 1
                          ? 'border-olive bg-olive text-white'
                          : 'border-sand-dark bg-white text-ink hover:bg-sand'
                      }`}
                    >
                      👍 Yes {tally.up > 0 ? `· ${tally.up}` : ''}
                    </button>
                    <button
                      type="button"
                      onClick={() => castVote(recipe.id, -1)}
                      disabled={saving === recipe.id}
                      className={`flex-1 rounded-full border px-4 py-3 text-sm font-semibold transition ${
                        myVote === -1
                          ? 'border-terracotta bg-terracotta text-white'
                          : 'border-sand-dark bg-white text-ink hover:bg-sand'
                      }`}
                    >
                      👎 No {tally.down > 0 ? `· ${tally.down}` : ''}
                    </button>
                  </div>
                  {tally.names.length > 0 ? (
                    <p className="mt-2 text-xs text-ink-soft">
                      {tally.names.slice(0, 5).join(', ')}
                      {tally.names.length > 5 ? ` +${tally.names.length - 5} more` : ''}
                    </p>
                  ) : null}
                </div>
              </li>
            );
          })}
        </ul>
      )}

      <p className="text-center text-xs text-ink-soft">
        Votes update instantly. Your name and picks are saved on this device.
      </p>
    </div>
  );
}
