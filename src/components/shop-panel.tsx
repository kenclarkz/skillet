'use client';

import { useState } from 'react';
import { btnPrimary, btnSecondary } from './ui';

interface MatchedItemView {
  display: string;
  query: string;
  searchUrl: string;
  confidence: number;
  product: {
    id: string;
    title: string;
    brand: string | null;
    priceText: string | null;
    imageUrl: string | null;
    url: string;
  } | null;
}

interface ShopResult {
  retailer: string;
  status: 'created' | 'link' | 'error';
  cartId?: string;
  url?: string;
  message: string;
  items: MatchedItemView[];
}

export function ShopPanel({
  planId,
  retailers,
  itemCount,
}: {
  planId: string;
  retailers: { id: string; displayName: string; configured: boolean }[];
  itemCount: number;
}) {
  const [retailerId, setRetailerId] = useState(retailers[0]?.id ?? 'walmart');
  const [busy, setBusy] = useState(false);
  const [result, setResult] = useState<ShopResult | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [checked, setChecked] = useState<Record<string, boolean>>({});

  const selectedRetailer = retailers.find((r) => r.id === retailerId);

  async function shop() {
    setBusy(true);
    setError(null);
    setResult(null);
    try {
      const res = await fetch('/api/shop', {
        method: 'POST',
        headers: { 'content-type': 'application/json' },
        body: JSON.stringify({ retailer: retailerId, planId }),
      });
      const json = (await res.json()) as { result?: ShopResult; error?: string };
      if (json.error) setError(json.error);
      if (json.result) setResult(json.result);
    } catch {
      setError('Could not reach the shopping service.');
    } finally {
      setBusy(false);
    }
  }

  async function copyList() {
    if (!result) return;
    const text = result.items.map((item) => `☐ ${item.display || item.query}`).join('\n');
    await navigator.clipboard.writeText(text);
  }

  return (
    <div className="space-y-5">
      <div className="rounded-2xl border border-sand-dark/70 bg-white p-5">
        <label className="block text-sm font-medium text-ink-soft" htmlFor="retailer">
          Choose a store
        </label>
        <div className="mt-2 flex flex-wrap gap-2">
          {retailers.map((retailer) => (
            <button
              key={retailer.id}
              type="button"
              onClick={() => {
                setRetailerId(retailer.id);
                setResult(null);
              }}
              className={`rounded-full border px-4 py-2 text-sm font-semibold ${
                retailerId === retailer.id
                  ? 'border-terracotta bg-terracotta text-white'
                  : 'border-sand-dark bg-white text-ink'
              }`}
            >
              {retailer.displayName}
              {retailer.configured ? '' : ' · links only'}
            </button>
          ))}
        </div>

        <p className="mt-3 text-sm text-ink-soft">
          {selectedRetailer?.configured
            ? `${selectedRetailer.displayName} API credentials detected. We will try to match products and create a cart; failures are reported honestly.`
            : `${selectedRetailer?.displayName ?? 'This store'} integration is not configured, so we generate real product search links instead of pretending to create a cart.`}
        </p>

        <div className="mt-4 flex flex-wrap items-center gap-3">
          <button type="button" onClick={shop} disabled={busy || itemCount === 0} className={btnPrimary}>
            {busy ? 'Matching products…' : `Shop ${itemCount} items`}
          </button>
          {result ? (
            <button type="button" onClick={copyList} className={btnSecondary}>
              Copy matched list
            </button>
          ) : null}
        </div>

        {itemCount === 0 ? (
          <p className="mt-3 text-sm text-terracotta-dark">
            Your list has no active items yet. Build the grocery list first.
          </p>
        ) : null}
        {error ? (
          <p className="mt-3 rounded-xl bg-terracotta/10 px-3 py-2 text-sm text-terracotta-dark">{error}</p>
        ) : null}
      </div>

      {result ? (
        <div className="space-y-4">
          <div
            className={`rounded-2xl px-4 py-3 text-sm ${
              result.status === 'created'
                ? 'bg-olive/10 text-olive-dark'
                : result.status === 'error'
                  ? 'bg-terracotta/10 text-terracotta-dark'
                  : 'bg-sand text-ink-soft'
            }`}
          >
            {result.message}
            {result.status === 'created' && result.url ? (
              <a
                href={result.url}
                target="_blank"
                rel="noreferrer noopener"
                className="ml-2 font-semibold underline"
              >
                Open cart ↗
              </a>
            ) : null}
          </div>

          <ul className="divide-y divide-sand-dark/60 overflow-hidden rounded-2xl border border-sand-dark/70 bg-white">
            {result.items.map((item, index) => (
              <li key={`${item.query}-${index}`} className="flex items-center gap-3 p-3">
                <input
                  type="checkbox"
                  checked={checked[index] ?? false}
                  onChange={(e) => setChecked((prev) => ({ ...prev, [index]: e.target.checked }))}
                  className="h-5 w-5 accent-[#6b7a4f]"
                />
                <div className="min-w-0 flex-1">
                  <p className="text-sm font-medium text-ink">{item.display || item.query}</p>
                  {item.product ? (
                    <p className="truncate text-xs text-ink-soft">
                      {item.product.title}
                      {item.product.priceText ? ` · ${item.product.priceText}` : ''}
                      {` · ${Math.round(item.confidence * 100)}% match`}
                    </p>
                  ) : (
                    <p className="text-xs text-ink-soft">No confident product match — search instead.</p>
                  )}
                </div>
                <a
                  href={item.product?.url ?? item.searchUrl}
                  target="_blank"
                  rel="noreferrer noopener"
                  className="shrink-0 rounded-full border border-sand-dark px-3 py-1.5 text-xs font-semibold text-ink hover:bg-sand"
                >
                  {item.product ? 'Open ↗' : 'Search ↗'}
                </a>
              </li>
            ))}
          </ul>

          <p className="text-xs text-ink-soft">
            Product data and prices come live from the retailer API when configured. Nothing here is
            simulated.
          </p>
        </div>
      ) : null}

      <details className="rounded-2xl border border-sand-dark/70 bg-white p-4">
        <summary className="cursor-pointer text-sm font-semibold text-ink">
          How the store integrations work
        </summary>
        <div className="mt-2 space-y-2 text-sm text-ink-soft">
          <p>
            <strong>Walmart:</strong> live product search uses the Walmart Affiliate API
            (<code className="rounded bg-sand px-1">WALMART_CONSUMER_ID</code> +{' '}
            <code className="rounded bg-sand px-1">WALMART_PRIVATE_KEY</code>). Cart creation is only
            used when a cart endpoint is configured and confirms the cart.
          </p>
          <p>
            <strong>Instacart:</strong> live mode uses the Instacart Connect partner API (
            <code className="rounded bg-sand px-1">INSTACART_API_KEY</code>). Without partner access,
            we provide search links.
          </p>
          <p>
            In both cases, if a call fails you&apos;ll see the real error and can shop manually with the
            links above.
          </p>
        </div>
      </details>
    </div>
  );
}
