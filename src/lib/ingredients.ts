// Parses free-form recipe ingredient text into structured ingredients.
// Works on strings like: "1 1/2 cups all-purpose flour, sifted"
//                       "2 large eggs"
//                       "salt and pepper to taste"
//                       "1 (14 oz) can diced tomatoes"

import type { Ingredient } from '@/lib/types';

const QTY_PATTERN =
  /^(\d+\s+\d+\/\d+|\d+\/\d+|\d+(?:[.,]\d+)?|\.(?:\d+)?)\s*/;

const UNIT_PATTERN = /^([a-zA-Z][a-zA-Z.]*)\s+/;

const KNOWN_UNITS = new Set([
  'cup', 'cups', 'tsp', 'teaspoon', 'teaspoons', 'tbsp', 'tablespoon', 'tablespoons',
  'oz', 'ounce', 'ounces', 'lb', 'lbs', 'pound', 'pounds', 'g', 'gram', 'grams',
  'kg', 'kilogram', 'kilograms', 'ml', 'milliliter', 'milliliters', 'l', 'liter',
  'liters', 'clove', 'cloves', 'can', 'cans', 'package', 'packages', 'pkg',
  'bunch', 'bunches', 'head', 'heads', 'stick', 'sticks', 'slice', 'slices',
  'piece', 'pieces', 'pinch', 'pinches', 'dash', 'dashes', 'sprig', 'sprigs',
  'fl', 'fluid', 'pint', 'pints', 'quart', 'quarts', 'gallon', 'gallons',
]);

/** Normalize a fraction or decimal quantity string to a canonical decimal string. */
function normalizeQty(raw: string): string {
  const cleaned = raw.trim().replace(/,/g, '.');
  const mixed = cleaned.match(/^(\d+)\s+(\d+)\/(\d+)$/);
  if (mixed) {
    const whole = parseInt(mixed[1], 10);
    const num = parseInt(mixed[2], 10);
    const den = parseInt(mixed[3], 10);
    if (den !== 0) return String(whole + num / den);
  }
  const frac = cleaned.match(/^(\d+)\/(\d+)$/);
  if (frac) {
    const num = parseInt(frac[1], 10);
    const den = parseInt(frac[2], 10);
    if (den !== 0) return String(num / den);
  }
  return cleaned;
}

/**
 * Parse a single ingredient line into a structured Ingredient.
 */
export function parseIngredientLine(line: string): Ingredient {
  let rest = line.trim();
  let qty: string | null = null;
  let unit: string | null = null;
  let note: string | null = null;

  // Split off trailing prep notes after a comma: "1 onion, diced"
  const commaIdx = rest.indexOf(',');
  let prepNote: string | null = null;
  if (commaIdx > -1) {
    prepNote = rest.slice(commaIdx + 1).trim() || null;
    rest = rest.slice(0, commaIdx).trim();
  }

  // Leading quantity
  const qtyMatch = rest.match(QTY_PATTERN);
  if (qtyMatch) {
    qty = normalizeQty(qtyMatch[1]);
    rest = rest.slice(qtyMatch[0].length).trim();
  }

  // Optional parenthetical size, e.g. "1 (14 oz) can diced tomatoes"
  const parenMatch = rest.match(/^\(([^)]+)\)\s*/);
  if (parenMatch) {
    // Pull a quantity out of the parenthetical if present.
    const inner = parenMatch[1];
    const innerQty = inner.match(QTY_PATTERN);
    if (innerQty && !qty) qty = normalizeQty(innerQty[1]);
    rest = rest.slice(parenMatch[0].length).trim();
    note = note ? `${note} (${inner})` : `(${inner})`;
  }

  // Unit
  const unitMatch = rest.match(UNIT_PATTERN);
  if (unitMatch) {
    const candidate = unitMatch[1].toLowerCase().replace(/\.$/, '');
    if (KNOWN_UNITS.has(candidate)) {
      // "fl oz" / "fluid ounce" is two words
      const twoWord = rest.match(/^(fl|fluid)\s+(oz|ounce|ounces)\s+/i);
      if (twoWord) {
        unit = `${twoWord[1].toLowerCase()} ${twoWord[2].toLowerCase().replace(/\.$/, '')}`;
        rest = rest.slice(twoWord[0].length).trim();
      } else {
        unit = candidate;
        rest = rest.slice(unitMatch[0].length).trim();
      }
    }
  }

  // Drop trailing size descriptors like "or as needed" that would pollute the name
  const name = rest.replace(/\s*\([^)]*\)\s*$/, '').trim();

  if (prepNote) {
    note = note ? `${note}, ${prepNote}` : prepNote;
  }

  // If we captured no qty and no unit, the whole line is the name (e.g. "salt to taste")
  if (!qty && !unit && !name) {
    return { qty: null, unit: null, name: line.trim(), note: null };
  }

  return {
    qty: qty ?? null,
    unit: unit ?? null,
    name: name || line.trim(),
    note: note ?? null,
  };
}

/**
 * Parse a block of ingredient lines (one per line) into structured ingredients.
 */
export function parseIngredientText(text: string): Ingredient[] {
  return text
    .split('\n')
    .map((l) => l.trim())
    .filter(Boolean)
    .map(parseIngredientLine);
}

/**
 * Produce a stable, comparable name key for pantry matching and grocery merging.
 * Lowercases, strips plural 's', collapses whitespace and punctuation.
 */
export function normalizeIngredientName(name: string): string {
  return name
    .toLowerCase()
    .replace(/[^a-z0-9\s]/g, ' ')
    .replace(/\s+/g, ' ')
    .trim()
    // crude singularization for matching purposes
    .replace(/ies$/, 'y')
    .replace(/oes$/, 'o')
    .replace(/sses$/, 'ss')
    .replace(/s$/, '');
}

/**
 * Parse a decimal number from a qty string, returning null if not numeric.
 */
export function qtyToNumber(qty: string | null | undefined): number | null {
  if (!qty) return null;
  const n = parseFloat(qty.replace(/,/g, '.'));
  return Number.isFinite(n) ? n : null;
}
