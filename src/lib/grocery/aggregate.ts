// Aggregates recipe ingredients into a combined grocery list,
// merging quantities across recipes and flagging pantry staples.

import type { Ingredient } from '@/lib/types';
import { normalizeIngredientName, qtyToNumber } from '@/lib/ingredients';
import { resolveUnit, toBase, fromBase, type UnitFamily } from './units';

export interface SourceIngredient extends Ingredient {
  recipeId: string;
  recipeTitle: string;
  /** Multiplier applied to the ingredient's quantities (servings scaling). */
  scale?: number;
}

export interface AggregatedGroceryItem {
  /** Stable merge key: normalized name + unit family. */
  key: string;
  name: string;
  normalized_name: string;
  /** Numeric quantity in the display unit, or null if unknown. */
  qty: number | null;
  /** Display unit (canonical). Empty string for plain counts. */
  unit: string;
  family: UnitFamily;
  recipe_ids: string[];
  recipes: { id: string; title: string }[];
  in_pantry: boolean;
  /** True when some contributing lines had no quantity ("salt to taste"). */
  missing_qty: boolean;
  /** Units were incompatible so items could not be merged. */
  split_note?: string;
}

interface Draft {
  key: string;
  name: string;
  normalized_name: string;
  baseTotal: number;
  hasNumeric: boolean;
  hasNonNumeric: boolean;
  unitVotes: Map<string, number>;
  recipeIds: Set<string>;
  recipes: Map<string, string>;
  family: UnitFamily;
  unitTexts: Set<string>;
}

/**
 * Group and merge ingredients from many recipes into grocery items.
 * Pantry staples (matched by normalized name) are flagged `in_pantry`.
 */
export function aggregateGroceries(
  ingredients: SourceIngredient[],
  opts: { pantry?: Set<string> } = {}
): AggregatedGroceryItem[] {
  const pantry = opts.pantry ?? new Set<string>();
  const drafts = new Map<string, Draft>();

  for (const ing of ingredients) {
    const normalized = normalizeIngredientName(ing.name);
    if (!normalized) continue;

    const scale = ing.scale ?? 1;
    const unitInfo = resolveUnit(ing.unit);
    const family = unitInfo.family;

    // Unknown-family units with differing text never merge across variants.
    const unitKey = family === 'unknown' && unitInfo.canonical ? `|${unitInfo.canonical}` : '';
    const key = `${normalized}|${family}${unitKey}`;

    let draft = drafts.get(key);
    if (!draft) {
      draft = {
        key,
        name: ing.name.trim(),
        normalized_name: normalized,
        baseTotal: 0,
        hasNumeric: false,
        hasNonNumeric: false,
        unitVotes: new Map(),
        recipes: new Map(),
        recipeIds: new Set(),
        family,
        unitTexts: new Set(),
      };
      drafts.set(key, draft);
    }

    draft.recipeIds.add(ing.recipeId);
    draft.recipes.set(ing.recipeId, ing.recipeTitle);
    if (ing.unit) draft.unitVotes.set(ing.unit, (draft.unitVotes.get(ing.unit) ?? 0) + 1);
    draft.unitTexts.add(ing.unit ?? '');

    const num = qtyToNumber(ing.qty);
    if (num === null) {
      draft.hasNonNumeric = true;
    } else {
      draft.hasNumeric = true;
      const { base } = toBase(num * scale, ing.unit);
      draft.baseTotal += base;
    }
  }

  const items: AggregatedGroceryItem[] = [];

  for (const d of drafts.values()) {
    // Choose display unit: most frequently used among contributors.
    let displayUnit = '';
    let bestVotes = -1;
    for (const [unit, votes] of d.unitVotes) {
      if (votes > bestVotes) {
        bestVotes = votes;
        displayUnit = unit;
      }
    }

    let qty: number | null = null;
    if (d.hasNumeric) {
      qty = d.family === 'unknown' ? d.baseTotal : fromBase(d.baseTotal, displayUnit);
      // Avoid tiny fractional remainders from unit conversion.
      if (Math.abs(qty - Math.round(qty)) < 0.01) qty = Math.round(qty * 1000) / 1000;
      else qty = Math.round(qty * 10000) / 10000;
    }

    const canonicalUnit =
      d.family === 'unknown' ? displayUnit : resolveUnit(displayUnit).canonical;

    items.push({
      key: d.key,
      name: d.name,
      normalized_name: d.normalized_name,
      qty,
      unit: canonicalUnit,
      family: d.family,
      recipe_ids: Array.from(d.recipeIds),
      recipes: Array.from(d.recipes, ([id, title]) => ({ id, title })),
      in_pantry: pantry.has(d.normalized_name),
      missing_qty: d.hasNonNumeric,
      split_note: d.hasNonNumeric && d.hasNumeric ? 'partial quantity' : undefined,
    });
  }

  items.sort((a, b) => {
    // Pantry staples sink to the bottom, then alphabetical.
    if (a.in_pantry !== b.in_pantry) return a.in_pantry ? 1 : -1;
    return a.name.localeCompare(b.name);
  });

  return items;
}

/** Human-readable quantity + unit, e.g. "1 1/2 cups" or "3" or "to taste". */
export function formatQuantity(item: { qty: number | null; unit: string; missing_qty?: boolean }): string {
  if (item.qty === null) {
    return item.missing_qty ? 'to taste' : '';
  }
  const q = formatNumber(item.qty);
  const unit = item.unit;
  if (!unit) return q;
  return `${q} ${unit}${item.qty !== 1 && !unit.endsWith('s') && unit !== 'lb' && unit !== 'oz' && unit !== 'fl oz' && unit !== 'tbsp' && unit !== 'tsp' ? 's' : ''}`.trim();
}

/** Format a number as a friendly cooking fraction where possible. */
export function formatNumber(n: number): string {
  if (Number.isInteger(n)) return String(n);
  const whole = Math.floor(n);
  const frac = n - whole;
  const candidates: [number, string][] = [
    [1 / 8, '1/8'], [1 / 6, '1/6'], [1 / 5, '1/5'], [1 / 4, '1/4'],
    [1 / 3, '1/3'], [3 / 8, '3/8'], [1 / 2, '1/2'], [5 / 8, '5/8'],
    [2 / 3, '2/3'], [3 / 4, '3/4'], [5 / 6, '5/6'], [7 / 8, '7/8'],
  ];
  for (const [value, label] of candidates) {
    if (Math.abs(frac - value) < 0.025) {
      return whole > 0 ? `${whole} ${label}` : label;
    }
  }
  const rounded = Math.round(n * 100) / 100;
  return String(rounded);
}
