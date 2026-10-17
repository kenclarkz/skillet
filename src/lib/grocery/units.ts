// Unit definitions and conversions for grocery quantity math.
// Families: volume (base ml), weight (base g), count (base each), unknown.

export type UnitFamily = 'volume' | 'weight' | 'count' | 'unknown';

interface UnitDef {
  /** Canonical short form used for display/storage. */
  canonical: string;
  family: UnitFamily;
  /** Multiply a value in this unit by `factor` to get the family base unit. */
  factor?: number;
  /** Relative display size within family (higher = larger unit). */
  size?: number;
}

const UNIT_DEFS: Record<string, UnitDef> = {
  // volume
  ml: { canonical: 'ml', family: 'volume', factor: 1, size: 0.001 },
  milliliter: { canonical: 'ml', family: 'volume', factor: 1, size: 0.001 },
  millilitre: { canonical: 'ml', family: 'volume', factor: 1, size: 0.001 },
  l: { canonical: 'l', family: 'volume', factor: 1000, size: 1 },
  liter: { canonical: 'l', family: 'volume', factor: 1000, size: 1 },
  litre: { canonical: 'l', family: 'volume', factor: 1000, size: 1 },
  tsp: { canonical: 'tsp', family: 'volume', factor: 4.92892, size: 0.02 },
  teaspoons: { canonical: 'tsp', family: 'volume', factor: 4.92892, size: 0.02 },
  teaspoon: { canonical: 'tsp', family: 'volume', factor: 4.92892, size: 0.02 },
  tbsp: { canonical: 'tbsp', family: 'volume', factor: 14.7868, size: 0.06 },
  tablespoons: { canonical: 'tbsp', family: 'volume', factor: 14.7868, size: 0.06 },
  tablespoon: { canonical: 'tbsp', family: 'volume', factor: 14.7868, size: 0.06 },
  fl_oz: { canonical: 'fl oz', family: 'volume', factor: 29.5735, size: 0.1 },
  floz: { canonical: 'fl oz', family: 'volume', factor: 29.5735, size: 0.1 },
  'fluid ounce': { canonical: 'fl oz', family: 'volume', factor: 29.5735, size: 0.1 },
  'fluid ounces': { canonical: 'fl oz', family: 'volume', factor: 29.5735, size: 0.1 },
  cup: { canonical: 'cup', family: 'volume', factor: 236.588, size: 1 },
  cups: { canonical: 'cup', family: 'volume', factor: 236.588, size: 1 },
  pint: { canonical: 'pint', family: 'volume', factor: 473.176, size: 2 },
  pints: { canonical: 'pint', family: 'volume', factor: 473.176, size: 2 },
  quart: { canonical: 'quart', family: 'volume', factor: 946.353, size: 4 },
  quarts: { canonical: 'quart', family: 'volume', factor: 946.353, size: 4 },
  gallon: { canonical: 'gallon', family: 'volume', factor: 3785.41, size: 16 },
  gallons: { canonical: 'gallon', family: 'volume', factor: 3785.41, size: 16 },

  // weight
  g: { canonical: 'g', family: 'weight', factor: 1, size: 0.001 },
  gram: { canonical: 'g', family: 'weight', factor: 1, size: 0.001 },
  grams: { canonical: 'g', family: 'weight', factor: 1, size: 0.001 },
  kg: { canonical: 'kg', family: 'weight', factor: 1000, size: 1 },
  kilogram: { canonical: 'kg', family: 'weight', factor: 1000, size: 1 },
  kilograms: { canonical: 'kg', family: 'weight', factor: 1000, size: 1 },
  oz: { canonical: 'oz', family: 'weight', factor: 28.3495, size: 0.03 },
  ounce: { canonical: 'oz', family: 'weight', factor: 28.3495, size: 0.03 },
  ounces: { canonical: 'oz', family: 'weight', factor: 28.3495, size: 0.03 },
  lb: { canonical: 'lb', family: 'weight', factor: 453.592, size: 1 },
  lbs: { canonical: 'lb', family: 'weight', factor: 453.592, size: 1 },
  pound: { canonical: 'lb', family: 'weight', factor: 453.592, size: 1 },
  pounds: { canonical: 'lb', family: 'weight', factor: 453.592, size: 1 },

  // count
  each: { canonical: '', family: 'count', factor: 1, size: 1 },
  clove: { canonical: 'clove', family: 'count', factor: 1, size: 1 },
  cloves: { canonical: 'clove', family: 'count', factor: 1, size: 1 },
  can: { canonical: 'can', family: 'count', factor: 1, size: 1 },
  cans: { canonical: 'can', family: 'count', factor: 1, size: 1 },
  package: { canonical: 'package', family: 'count', factor: 1, size: 1 },
  packages: { canonical: 'package', family: 'count', factor: 1, size: 1 },
  pkg: { canonical: 'package', family: 'count', factor: 1, size: 1 },
  bunch: { canonical: 'bunch', family: 'count', factor: 1, size: 1 },
  bunches: { canonical: 'bunch', family: 'count', factor: 1, size: 1 },
  head: { canonical: 'head', family: 'count', factor: 1, size: 1 },
  heads: { canonical: 'head', family: 'count', factor: 1, size: 1 },
  stick: { canonical: 'stick', family: 'count', factor: 1, size: 1 },
  sticks: { canonical: 'stick', family: 'count', factor: 1, size: 1 },
  slice: { canonical: 'slice', family: 'count', factor: 1, size: 1 },
  slices: { canonical: 'slice', family: 'count', factor: 1, size: 1 },
  piece: { canonical: 'piece', family: 'count', factor: 1, size: 1 },
  pieces: { canonical: 'piece', family: 'count', factor: 1, size: 1 },
  pinch: { canonical: 'pinch', family: 'count', factor: 1, size: 1 },
  pinches: { canonical: 'pinch', family: 'count', factor: 1, size: 1 },
  dash: { canonical: 'dash', family: 'count', factor: 1, size: 1 },
  dashes: { canonical: 'dash', family: 'count', factor: 1, size: 1 },
  sprig: { canonical: 'sprig', family: 'count', factor: 1, size: 1 },
  sprigs: { canonical: 'sprig', family: 'count', factor: 1, size: 1 },
  'pinch of': { canonical: 'pinch', family: 'count', factor: 1, size: 1 },
};

/** Resolve a raw unit string to its canonical form and family. */
export function resolveUnit(raw: string | null | undefined): {
  canonical: string;
  family: UnitFamily;
  factor: number;
  size: number;
} {
  if (!raw) {
    return { canonical: '', family: 'count', factor: 1, size: 1 };
  }
  const key = raw.trim().toLowerCase().replace(/\./g, '').replace(/\s+/g, ' ');
  const def = UNIT_DEFS[key];
  if (def && def.factor !== undefined && def.size !== undefined) {
    return { canonical: def.canonical, family: def.family, factor: def.factor, size: def.size };
  }
  return { canonical: raw.trim().toLowerCase(), family: 'unknown', factor: 1, size: 1 };
}

/** Convert a value expressed in `unit` into the family's base unit. */
export function toBase(value: number, unit: string | null | undefined): { base: number; family: UnitFamily } {
  const u = resolveUnit(unit);
  return { base: value * u.factor, family: u.family };
}

/** Convert a value in the family base unit back into `unit`. */
export function fromBase(base: number, unit: string | null | undefined): number {
  const u = resolveUnit(unit);
  return base / u.factor;
}

export function familyOf(unit: string | null | undefined): UnitFamily {
  return resolveUnit(unit).family;
}
