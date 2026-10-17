'use client';

import { useMemo, useState } from 'react';
import type { Ingredient } from '@/lib/types';
import { formatNumber } from '@/lib/grocery/aggregate';
import { qtyToNumber } from '@/lib/ingredients';
import { btnSecondary } from './ui';

/** Ingredient list with a live servings scaler for easy portion math. */
export function RecipeIngredients({
  ingredients,
  baseServings,
}: {
  ingredients: Ingredient[];
  baseServings: number;
}) {
  const [servings, setServings] = useState(baseServings);
  const scale = baseServings > 0 ? servings / baseServings : 1;

  const rows = useMemo(
    () =>
      ingredients.map((ing, index) => {
        const qty = qtyToNumber(ing.qty);
        const displayQty = qty === null ? ing.qty : formatNumber(qty * scale);
        return { key: `${ing.name}-${index}`, ing, displayQty };
      }),
    [ingredients, scale]
  );

  return (
    <div>
      <div className="mb-4 flex flex-wrap items-center gap-3 rounded-2xl bg-sand/70 px-4 py-3">
        <span className="text-sm font-medium text-ink">Servings</span>
        <div className="flex items-center gap-2">
          <button
            type="button"
            onClick={() => setServings((s) => Math.max(1, s - 1))}
            className="h-8 w-8 rounded-full border border-sand-dark bg-white text-lg leading-none text-ink"
            aria-label="Decrease servings"
          >
            −
          </button>
          <span className="min-w-8 text-center text-base font-semibold text-ink">{servings}</span>
          <button
            type="button"
            onClick={() => setServings((s) => Math.min(100, s + 1))}
            className="h-8 w-8 rounded-full border border-sand-dark bg-white text-lg leading-none text-ink"
            aria-label="Increase servings"
          >
            +
          </button>
        </div>
        {servings !== baseServings ? (
          <button type="button" onClick={() => setServings(baseServings)} className={btnSecondary}>
            Reset
          </button>
        ) : null}
      </div>

      <ul className="space-y-2">
        {rows.map(({ key, ing, displayQty }) => (
          <li key={key} className="flex gap-3 border-b border-sand-dark/50 pb-2 last:border-0">
            <span className="min-w-20 shrink-0 font-semibold text-terracotta-dark">
              {displayQty ? [displayQty, ing.unit].filter(Boolean).join(' ') : '—'}
            </span>
            <span className="text-ink">
              {ing.name}
              {ing.note ? <span className="text-ink-soft"> · {ing.note}</span> : null}
            </span>
          </li>
        ))}
      </ul>
    </div>
  );
}
