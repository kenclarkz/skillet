import { describe, expect, it } from 'vitest';
import { normalizeIngredientName, parseIngredientLine, parseIngredientText, qtyToNumber } from '@/lib/ingredients';
import { formatNumber, formatQuantity } from '@/lib/grocery/aggregate';

describe('parseIngredientLine', () => {
  it('parses mixed-number quantities with units', () => {
    const ing = parseIngredientLine('1 1/2 cups all-purpose flour');
    expect(ing.qty).toBe('1.5');
    expect(ing.unit).toBe('cups');
    expect(ing.name).toBe('all-purpose flour');
  });

  it('parses fractions and trailing prep notes', () => {
    const ing = parseIngredientLine('1/2 cup onion, diced');
    expect(ing.qty).toBe('0.5');
    expect(ing.unit).toBe('cup');
    expect(ing.name).toBe('onion');
    expect(ing.note).toBe('diced');
  });

  it('parses count items with adjectives but no unit', () => {
    const ing = parseIngredientLine('2 large eggs');
    expect(ing.qty).toBe('2');
    expect(ing.unit).toBeNull();
    expect(ing.name).toBe('large eggs');
  });

  it('parses quantity-only lines as notes', () => {
    const ing = parseIngredientLine('salt and pepper to taste');
    expect(ing.qty).toBeNull();
    expect(ing.unit).toBeNull();
    expect(ing.name).toBe('salt and pepper to taste');
  });

  it('parses parenthetical sizes', () => {
    const ing = parseIngredientLine('1 (14 oz) can diced tomatoes');
    expect(ing.qty).toBe('1');
    expect(ing.unit).toBe('can');
    expect(ing.name).toBe('diced tomatoes');
    expect(ing.note).toBe('(14 oz)');
  });

  it('handles two-word fluid ounce units', () => {
    const ing = parseIngredientLine('8 fl oz heavy cream');
    expect(ing.qty).toBe('8');
    expect(ing.unit).toBe('fl oz');
    expect(ing.name).toBe('heavy cream');
  });

  it('parses blocks of text', () => {
    const list = parseIngredientText('2 tbsp olive oil\n3 cloves garlic, minced\n\n1 lb ground beef');
    expect(list).toHaveLength(3);
    expect(list[1].name).toBe('garlic');
    expect(list[2].unit).toBe('lb');
  });
});

describe('normalizeIngredientName', () => {
  it('matches singular and plural forms', () => {
    expect(normalizeIngredientName('Carrots')).toBe(normalizeIngredientName('carrot'));
    expect(normalizeIngredientName('Tomatoes')).toBe(normalizeIngredientName('tomato'));
  });
});

describe('qtyToNumber', () => {
  it('returns null for non-numeric quantities', () => {
    expect(qtyToNumber('to taste')).toBeNull();
    expect(qtyToNumber(null)).toBeNull();
    expect(qtyToNumber('1.5')).toBe(1.5);
  });
});

describe('formatting', () => {
  it('formats decimals as cooking fractions', () => {
    expect(formatNumber(1.5)).toBe('1 1/2');
    expect(formatNumber(0.25)).toBe('1/4');
    expect(formatNumber(3)).toBe('3');
    expect(formatNumber(2.6667)).toBe('2 2/3');
  });

  it('includes pluralized units', () => {
    expect(formatQuantity({ qty: 2, unit: 'cup' })).toBe('2 cups');
    expect(formatQuantity({ qty: 1, unit: 'cup' })).toBe('1 cup');
    expect(formatQuantity({ qty: 3, unit: 'tbsp' })).toBe('3 tbsp');
    expect(formatQuantity({ qty: null, unit: '', missing_qty: true })).toBe('to taste');
  });
});
