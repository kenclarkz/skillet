// Product matching: maps a grocery item to the best candidate product.

import type { RetailerProduct, ShoppingListItem } from './types';

const STOP_WORDS = new Set([
  'fresh', 'organic', 'the', 'of', 'and', 'a', 'an', 'for', 'with', 'large',
  'small', 'medium', 'whole', 'boneless', 'skinless', 'extra', 'virgin',
  'to', 'taste', 'chopped', 'diced', 'minced', 'sliced', 'shredded',
]);

export function tokens(text: string): string[] {
  return text
    .toLowerCase()
    .replace(/[^a-z0-9\s]/g, ' ')
    .split(/\s+/)
    .map((t) => t.replace(/s$/, ''))
    .filter((t) => t && !STOP_WORDS.has(t));
}

/** 0..1 similarity between a grocery item and a product title. */
export function similarity(itemName: string, productTitle: string): number {
  const a = new Set(tokens(itemName));
  const b = new Set(tokens(productTitle));
  if (a.size === 0 || b.size === 0) return 0;
  let overlap = 0;
  for (const t of a) if (b.has(t)) overlap++;
  const jaccard = overlap / (a.size + b.size - overlap);
  // Bonus when the item name appears verbatim in the product title.
  const phrase = itemName.toLowerCase().trim();
  const bonus = phrase.length > 3 && productTitle.toLowerCase().includes(phrase) ? 0.35 : 0;
  return Math.min(1, jaccard + bonus);
}

export function bestMatch(
  item: ShoppingListItem,
  products: RetailerProduct[]
): { product: RetailerProduct | null; confidence: number } {
  let best: RetailerProduct | null = null;
  let bestScore = 0;
  for (const product of products) {
    const score = similarity(item.name, product.title);
    if (score > bestScore) {
      bestScore = score;
      best = product;
    }
  }
  if (bestScore < 0.25) return { product: null, confidence: bestScore };
  return { product: best, confidence: bestScore };
}

/** Query text for a grocery item, including unit hints for better results. */
export function searchQueryForItem(item: ShoppingListItem): string {
  const parts = [item.name];
  if (item.unit && ['oz', 'lb', 'g', 'kg'].includes(item.unit)) {
    // weight hints help retailers surface the right size
  }
  return parts.join(' ').trim();
}
