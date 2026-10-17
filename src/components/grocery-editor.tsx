'use client';

import Link from 'next/link';
import { useMemo, useState } from 'react';
import {
  addGroceryItem,
  deleteGroceryItem,
  markAsPantry,
  toggleGroceryItem,
} from '@/app/actions/grocery';
import type { GroceryItem } from '@/lib/types';
import { formatQuantity } from '@/lib/grocery/aggregate';
import { SubmitButton } from './submit-button';
import { btnSecondary, inputBase } from './ui';

function lineFor(item: GroceryItem): string {
  const qty = formatQuantity({ qty: item.qty, unit: item.unit ?? '', missing_qty: item.qty === null });
  return [qty, item.name].filter(Boolean).join(' ');
}

export function GroceryEditor({
  listId,
  planId,
  items,
}: {
  listId: string;
  planId: string;
  items: GroceryItem[];
}) {
  const [filter, setFilter] = useState<'all' | 'todo' | 'done'>('all');

  const stats = useMemo(() => {
    const active = items.filter((item) => !item.excluded);
    const done = active.filter((item) => item.checked).length;
    return { total: active.length, done };
  }, [items]);

  const visible = items.filter((item) => {
    if (filter === 'todo') return !item.checked && !item.excluded;
    if (filter === 'done') return item.checked && !item.excluded;
    return true;
  });

  const toBuy = visible.filter((item) => !item.in_pantry && !item.excluded);
  const pantry = visible.filter((item) => item.in_pantry || item.excluded);

  async function copyList() {
    const text = items
      .filter((item) => !item.excluded)
      .map((item) => `☐ ${lineFor(item)}`)
      .join('\n');
    await navigator.clipboard.writeText(text);
  }

  function downloadCsv() {
    const rows = [['item', 'quantity', 'unit', 'in pantry']];
    for (const item of items) {
      rows.push([item.name, item.qty != null ? String(item.qty) : '', item.unit ?? '', item.in_pantry ? 'yes' : 'no']);
    }
    const csv = rows
      .map((row) => row.map((cell) => `"${cell.replace(/"/g, '""')}"`).join(','))
      .join('\n');
    const blob = new Blob([csv], { type: 'text/csv;charset=utf-8' });
    const url = URL.createObjectURL(blob);
    const link = document.createElement('a');
    link.href = url;
    link.download = 'skillet-grocery-list.csv';
    link.click();
    URL.revokeObjectURL(url);
  }

  return (
    <div className="space-y-5">
      <div className="flex flex-wrap items-center gap-3 rounded-2xl bg-sand/70 px-4 py-3 no-print">
        <div className="flex-1">
          <div className="h-2 w-full overflow-hidden rounded-full bg-white">
            <div
              className="h-full rounded-full bg-olive transition-all"
              style={{ width: `${stats.total ? (stats.done / stats.total) * 100 : 0}%` }}
            />
          </div>
          <p className="mt-1 text-xs text-ink-soft">
            {stats.done} of {stats.total} picked up
          </p>
        </div>
        <div className="flex flex-wrap gap-2">
          {(['all', 'todo', 'done'] as const).map((key) => (
            <button
              key={key}
              type="button"
              onClick={() => setFilter(key)}
              className={`rounded-full px-3 py-1.5 text-xs font-semibold ${
                filter === key ? 'bg-terracotta text-white' : 'bg-white text-ink-soft'
              }`}
            >
              {key === 'all' ? 'All' : key === 'todo' ? 'To buy' : 'In cart'}
            </button>
          ))}
        </div>
      </div>

      <div className="flex flex-wrap gap-2 no-print">
        <button type="button" onClick={copyList} className={btnSecondary}>
          Copy list
        </button>
        <button type="button" onClick={downloadCsv} className={btnSecondary}>
          Download CSV
        </button>
        <button type="button" onClick={() => window.print()} className={btnSecondary}>
          Print
        </button>
        <Link href={`/grocery/${planId}/shop`} className={btnSecondary}>
          Shop online →
        </Link>
      </div>

      <section>
        <h2 className="mb-2 text-lg font-semibold text-ink">To buy ({toBuy.length})</h2>
        {toBuy.length === 0 ? (
          <p className="rounded-xl border border-dashed border-sand-dark bg-white/60 px-4 py-6 text-center text-sm text-ink-soft">
            Nothing left to buy in this view.
          </p>
        ) : (
          <ul className="divide-y divide-sand-dark/60 overflow-hidden rounded-2xl border border-sand-dark/70 bg-white">
            {toBuy.map((item) => (
              <li key={item.id} className="flex items-center gap-3 p-3">
                <form action={toggleGroceryItem} className="flex items-center">
                  <input type="hidden" name="list_id" value={listId} />
                  <input type="hidden" name="item_id" value={item.id} />
                  <input type="hidden" name="plan_id" value={planId} />
                  <input type="hidden" name="field" value="checked" />
                  <input type="hidden" name="value" value={item.checked ? 'false' : 'true'} />
                  <input
                    type="checkbox"
                    checked={item.checked}
                    onChange={(e) => e.currentTarget.form?.requestSubmit()}
                    className="h-5 w-5 accent-[#6b7a4f]"
                    aria-label={`Mark ${item.name} as in cart`}
                  />
                </form>
                <div className="min-w-0 flex-1">
                  <p className={`text-base ${item.checked ? 'text-ink-soft line-through' : 'text-ink'}`}>
                    {item.name}
                  </p>
                  <p className="text-xs text-ink-soft">
                    {formatQuantity({ qty: item.qty, unit: item.unit ?? '', missing_qty: item.qty === null }) ||
                      'as needed'}
                    {item.recipes && item.recipes.length > 0 ? ` · for ${item.recipes.length} recipe${item.recipes.length === 1 ? '' : 's'}` : ''}
                  </p>
                </div>
                <form action={markAsPantry} className="no-print">
                  <input type="hidden" name="item_id" value={item.id} />
                  <input type="hidden" name="plan_id" value={planId} />
                  <input type="hidden" name="name" value={item.name} />
                  <SubmitButton variant="ghost" pendingLabel="…" title="I already have this at home">
                    Have it
                  </SubmitButton>
                </form>
                <form action={deleteGroceryItem} className="no-print">
                  <input type="hidden" name="item_id" value={item.id} />
                  <input type="hidden" name="plan_id" value={planId} />
                  <SubmitButton variant="ghost" pendingLabel="…" title="Remove item">
                    ✕
                  </SubmitButton>
                </form>
              </li>
            ))}
          </ul>
        )}
      </section>

      {pantry.length > 0 ? (
        <section>
          <h2 className="mb-2 text-lg font-semibold text-ink">Pantry / skipped ({pantry.length})</h2>
          <ul className="divide-y divide-sand-dark/60 overflow-hidden rounded-2xl border border-sand-dark/70 bg-white">
            {pantry.map((item) => (
              <li key={item.id} className="flex items-center gap-3 p-3">
                <form action={toggleGroceryItem} className="flex items-center">
                  <input type="hidden" name="list_id" value={listId} />
                  <input type="hidden" name="item_id" value={item.id} />
                  <input type="hidden" name="plan_id" value={planId} />
                  <input type="hidden" name="field" value="excluded" />
                  <input type="hidden" name="value" value={item.excluded ? 'false' : 'true'} />
                  <input
                    type="checkbox"
                    checked={!item.excluded}
                    onChange={(e) => e.currentTarget.form?.requestSubmit()}
                    className="h-5 w-5 accent-[#c4532d]"
                    aria-label={`Include ${item.name}`}
                  />
                </form>
                <div className="min-w-0 flex-1">
                  <p className="text-base text-ink-soft">{item.name}</p>
                  <p className="text-xs text-ink-soft">
                    {item.in_pantry ? 'pantry staple — excluded' : 'excluded'}
                  </p>
                </div>
              </li>
            ))}
          </ul>
        </section>
      ) : null}

      <form action={addGroceryItem} className="flex flex-wrap items-end gap-3 rounded-2xl border border-sand-dark/70 bg-white p-4 no-print">
        <input type="hidden" name="list_id" value={listId} />
        <input type="hidden" name="plan_id" value={planId} />
        <div className="min-w-40 flex-1">
          <label className="block text-sm font-medium text-ink-soft" htmlFor="new-item-name">
            Add an item
          </label>
          <input id="new-item-name" name="name" required className={inputBase} placeholder="Paper towels" />
        </div>
        <div className="w-24">
          <label className="block text-sm font-medium text-ink-soft" htmlFor="new-item-qty">
            Qty
          </label>
          <input id="new-item-qty" name="qty" type="number" step="any" className={inputBase} />
        </div>
        <div className="w-24">
          <label className="block text-sm font-medium text-ink-soft" htmlFor="new-item-unit">
            Unit
          </label>
          <input id="new-item-unit" name="unit" className={inputBase} placeholder="ct" />
        </div>
        <SubmitButton variant="secondary" pendingLabel="Adding…">
          Add
        </SubmitButton>
      </form>
    </div>
  );
}
