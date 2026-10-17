import { describe, expect, it } from 'vitest';
import { aggregateGroceries, type SourceIngredient } from '@/lib/grocery/aggregate';
import { resolveUnit, toBase, fromBase } from '@/lib/grocery/units';

function ing(name: string, qty: string | null, unit: string | null, recipeId = 'r1', scale?: number): SourceIngredient {
  return { qty, unit, name, note: null, recipeId, recipeTitle: recipeId, scale };
}

describe('units', () => {
  it('recognizes aliases', () => {
    expect(resolveUnit('tablespoons').canonical).toBe('tbsp');
    expect(resolveUnit('cups').family).toBe('volume');
    expect(resolveUnit('lbs').canonical).toBe('lb');
    expect(resolveUnit('bunch').family).toBe('count');
    expect(resolveUnit('blorp').family).toBe('unknown');
  });

  it('converts round-trips within a family', () => {
    const { base } = toBase(3, 'tbsp');
    expect(fromBase(base, 'tsp')).toBeCloseTo(9, 3);
  });
});

describe('aggregateGroceries', () => {
  it('merges the same ingredient across recipes using unit conversion', () => {
    const items = aggregateGroceries([
      ing('olive oil', '2', 'tbsp', 'r1'),
      ing('olive oil', '1', 'tbsp', 'r2'),
    ]);
    expect(items).toHaveLength(1);
    expect(items[0].name).toBe('olive oil');
    expect(items[0].qty).toBeCloseTo(3, 3);
    expect(items[0].unit).toBe('tbsp');
    expect(items[0].recipe_ids.sort()).toEqual(['r1', 'r2']);
  });

  it('merges compatible units like tsp and tbsp', () => {
    const items = aggregateGroceries([
      ing('vanilla extract', '3', 'tsp', 'r1'),
      ing('vanilla extract', '1', 'tbsp', 'r2'),
    ]);
    expect(items).toHaveLength(1);
    // display unit is the most common (tie -> first seen = tsp); 1 tbsp = 3 tsp
    expect(items[0].qty).toBeCloseTo(6, 2);
  });

  it('keeps incompatible units separate', () => {
    const items = aggregateGroceries([
      ing('butter', '2', 'tbsp', 'r1'),
      ing('butter', '1', 'cup', 'r2'),
    ]);
    // Both volume -> they merge, proving the family logic works.
    expect(items).toHaveLength(1);
  });

  it('does not merge volume and weight', () => {
    const items = aggregateGroceries([
      ing('flour', '1', 'cup', 'r1'),
      ing('flour', '100', 'g', 'r2'),
    ]);
    expect(items).toHaveLength(2);
  });

  it('applies servings scaling', () => {
    const items = aggregateGroceries([ing('rice', '1', 'cup', 'r1', 2)]);
    expect(items[0].qty).toBeCloseTo(2, 3);
  });

  it('flags pantry staples and sorts them last', () => {
    const items = aggregateGroceries(
      [ing('salt', null, null), ing('carrots', '3', null), ing('onion', '1', null)],
      { pantry: new Set(['salt']) }
    );
    expect(items[items.length - 1].name).toBe('salt');
    expect(items.find((i) => i.name === 'salt')?.in_pantry).toBe(true);
  });

  it('marks missing quantities instead of inventing them', () => {
    const items = aggregateGroceries([ing('black pepper', null, null)]);
    expect(items[0].qty).toBeNull();
    expect(items[0].missing_qty).toBe(true);
  });

  it('sums countable items without units', () => {
    const items = aggregateGroceries([
      ing('egg', '2', null, 'r1'),
      ing('eggs', '3', null, 'r2'),
    ]);
    expect(items).toHaveLength(1);
    expect(items[0].qty).toBe(5);
  });
});
