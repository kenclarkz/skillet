// Extracts recipe data from HTML: JSON-LD (schema.org/Recipe), microdata, and
// Open Graph / meta fallbacks. Returns an editable draft plus warnings.

import type { Ingredient } from '@/lib/types';
import { parseIngredientLine } from '@/lib/ingredients';

export interface ImportedRecipeDraft {
  title: string;
  description: string | null;
  photo_url: string | null;
  prep_minutes: number | null;
  cook_minutes: number | null;
  servings: number;
  source_url: string;
  tags: string[];
  ingredients: Ingredient[];
  instructions: string[];
  /** How the data was found. */
  method: 'json-ld' | 'microdata' | 'metadata' | 'none';
}

const ISO_DURATION = /^P(?:(\d+)D)?(?:T(?:(\d+)H)?(?:(\d+)M)?(?:([\d.]+)S)?)?$/i;

/** Parse an ISO-8601 duration ("PT1H30M", "PT45M") into minutes. */
export function parseIsoDuration(value: unknown): number | null {
  if (typeof value !== 'string') return null;
  const match = value.trim().match(ISO_DURATION);
  if (!match) {
    const hours = value.match(/(\d+)\s*h/i);
    const mins = value.match(/(\d+)\s*m/i);
    if (hours || mins) {
      return (hours ? parseInt(hours[1], 10) * 60 : 0) + (mins ? parseInt(mins[1], 10) : 0);
    }
    return null;
  }
  const [, days, hours, minutes] = match;
  const total = (days ? parseInt(days, 10) * 1440 : 0) + (hours ? parseInt(hours, 10) * 60 : 0) + (minutes ? parseInt(minutes, 10) : 0);
  return total > 0 ? total : null;
}

/** Extract a numeric serving count from values like "4", "4 servings", ["4"]. */
export function parseYield(value: unknown): number | null {
  if (value == null) return null;
  const raw = Array.isArray(value) ? value[0] : value;
  if (typeof raw === 'number') return raw > 0 ? Math.round(raw) : null;
  if (typeof raw !== 'string') return null;
  const match = raw.match(/(\d+)/);
  if (!match) return null;
  const n = parseInt(match[1], 10);
  return n > 0 ? n : null;
}

function firstString(value: unknown): string | null {
  if (typeof value === 'string' && value.trim()) return value.trim();
  if (Array.isArray(value)) {
    for (const v of value) {
      const s = firstString(v);
      if (s) return s;
    }
  }
  if (value && typeof value === 'object' && 'url' in (value as Record<string, unknown>)) {
    return firstString((value as Record<string, unknown>).url);
  }
  if (value && typeof value === 'object' && 'text' in (value as Record<string, unknown>)) {
    return firstString((value as Record<string, unknown>).text);
  }
  return null;
}

function flattenInstructions(value: unknown, out: string[] = []): string[] {
  if (typeof value === 'string') {
    for (const line of value.split(/\r?\n+/)) {
      const trimmed = line.trim().replace(/^\d+[.)]\s*/, '');
      if (trimmed) out.push(trimmed);
    }
    return out;
  }
  if (Array.isArray(value)) {
    for (const item of value) flattenInstructions(item, out);
    return out;
  }
  if (value && typeof value === 'object') {
    const obj = value as Record<string, unknown>;
    if (Array.isArray(obj.itemListElement)) {
      flattenInstructions(obj.itemListElement, out);
    } else if (typeof obj.text === 'string' && obj.text.trim()) {
      out.push(obj.text.trim());
    } else if (typeof obj.name === 'string' && obj.name.trim() && !obj['@type']) {
      out.push(obj.name.trim());
    }
  }
  return out;
}

function asRecipeNode(node: unknown, depth = 0): Record<string, unknown> | null {
  if (!node || typeof node !== 'object' || depth > 6) return null;
  if (Array.isArray(node)) {
    for (const item of node) {
      const found = asRecipeNode(item, depth + 1);
      if (found) return found;
    }
    return null;
  }
  const obj = node as Record<string, unknown>;
  const type = obj['@type'];
  const types = Array.isArray(type) ? type.map(String) : [String(type)];
  if (types.some((t) => t.toLowerCase() === 'recipe')) return obj;
  if (Array.isArray(obj['@graph'])) return asRecipeNode(obj['@graph'], depth + 1);
  return null;
}

function extractJsonLdRecipes(html: string): Record<string, unknown>[] {
  const results: Record<string, unknown>[] = [];
  const scriptRegex = /<script[^>]*type=["']application\/ld\+json["'][^>]*>([\s\S]*?)<\/script>/gi;
  let match: RegExpExecArray | null;
  while ((match = scriptRegex.exec(html))) {
    const body = match[1].trim().replace(/^<!--/, '').replace(/-->$/, '');
    if (!body) continue;
    try {
      const parsed = JSON.parse(body);
      const node = asRecipeNode(parsed);
      if (node) results.push(node);
    } catch {
      // Malformed JSON-LD is common; ignore and try the next block.
    }
  }
  return results;
}

function decodeEntities(input: string): string {
  const named: Record<string, string> = {
    amp: '&', lt: '<', gt: '>', quot: '"', apos: "'", nbsp: ' ',
    frac12: '½', frac14: '¼', frac34: '¾', deg: '°', rsquo: '’', lsquo: '‘',
    rdquo: '”', ldquo: '“', mdash: '—', ndash: '–',
  };
  return input
    .replace(/&#x([0-9a-f]+);/gi, (_, hex) => String.fromCodePoint(parseInt(hex, 16)))
    .replace(/&#(\d+);/g, (_, dec) => String.fromCodePoint(parseInt(dec, 10)))
    .replace(/&([a-z0-9]+);/gi, (m, name: string) => named[name.toLowerCase()] ?? m);
}

function stripTags(html: string): string {
  return decodeEntities(html.replace(/<[^>]*>/g, ' ')).replace(/\s+/g, ' ').trim();
}

function metaContent(html: string, names: string[]): string | null {
  for (const name of names) {
    const pattern = new RegExp(
      `<meta[^>]+(?:property|name|itemprop)=["']${name}["'][^>]*>`,
      'i'
    );
    const tag = html.match(pattern);
    if (tag) {
      const content = tag[0].match(/content=["']([^"']*)["']/i);
      if (content?.[1]) return decodeEntities(content[1]).trim();
    }
    // also content-before-attribute ordering
    const reversed = new RegExp(
      `<meta[^>]+content=["']([^"']*)["'][^>]*(?:property|name|itemprop)=["']${name}["'][^>]*>`,
      'i'
    );
    const alt = html.match(reversed);
    if (alt?.[1]) return decodeEntities(alt[1]).trim();
  }
  return null;
}

function extractMicrodata(html: string): { ingredients: string[]; instructions: string[]; yieldText: string | null } {
  const ingredients: string[] = [];
  const instructions: string[] = [];
  const ingredientRegex = /<(?:li|span|div|p)[^>]*itemprop=["']recipeIngredient["'][^>]*>([\s\S]*?)<\/(?:li|span|div|p)>/gi;
  let m: RegExpExecArray | null;
  while ((m = ingredientRegex.exec(html))) {
    const text = stripTags(m[1]);
    if (text) ingredients.push(text);
  }
  const instructionRegex = /<(?:li|span|div|p)[^>]*itemprop=["'](?:recipeInstructions|text)["'][^>]*>([\s\S]*?)<\/(?:li|span|div|p)>/gi;
  while ((m = instructionRegex.exec(html))) {
    const text = stripTags(m[1]);
    if (text && text.length > 2) instructions.push(text);
  }
  const yieldText = metaContent(html, ['recipeYield', 'yield']);
  return { ingredients, instructions, yieldText };
}

function absolutize(url: string | null, base: string): string | null {
  if (!url) return null;
  try {
    return new URL(url, base).toString();
  } catch {
    return null;
  }
}

/**
 * Parse recipe details out of an HTML document.
 */
export function parseRecipeHtml(html: string, sourceUrl: string): ImportedRecipeDraft {
  const jsonLd = extractJsonLdRecipes(html);

  if (jsonLd.length > 0) {
    const node = jsonLd[0];
    const rawIngredients = node.recipeIngredient ?? node.ingredients;
    const ingredients: Ingredient[] = Array.isArray(rawIngredients)
      ? rawIngredients
          .map((i) => (typeof i === 'string' ? i : firstString(i)))
          .filter((i): i is string => !!i)
          .map((line) => parseIngredientLine(stripTags(line)))
      : [];

    const instructions = flattenInstructions(node.recipeInstructions);
    const photo = firstString(node.image) ?? firstString(node.thumbnailUrl);
    const tagsRaw = node.recipeCategory ?? node.keywords ?? node.recipeCuisine;
    const tags = Array.isArray(tagsRaw)
      ? tagsRaw.flatMap((t) => String(t).split(',').map((s) => s.trim()))
      : typeof tagsRaw === 'string'
        ? tagsRaw.split(',').map((s) => s.trim())
        : [];

    const title = firstString(node.name) ?? stripTags(html.match(/<title[^>]*>([\s\S]*?)<\/title>/i)?.[1] ?? '') ?? '';

    return {
      title: title || 'Imported recipe',
      description: firstString(node.description),
      photo_url: absolutize(photo, sourceUrl),
      prep_minutes: parseIsoDuration(node.prepTime),
      cook_minutes: parseIsoDuration(node.cookTime) ?? parseIsoDuration(node.totalTime),
      servings: parseYield(node.recipeYield) ?? 4,
      source_url: sourceUrl,
      tags: tags.filter(Boolean).slice(0, 8),
      ingredients,
      instructions: dedupeInOrder(instructions).slice(0, 60),
      method: 'json-ld',
    };
  }

  // Microdata fallback
  const micro = extractMicrodata(html);
  if (micro.ingredients.length > 0 || micro.instructions.length > 0) {
    return {
      title: metaContent(html, ['og:title', 'twitter:title']) ?? stripTags(html.match(/<title[^>]*>([\s\S]*?)<\/title>/i)?.[1] ?? '') ?? 'Imported recipe',
      description: metaContent(html, ['og:description', 'description']),
      photo_url: absolutize(metaContent(html, ['og:image', 'twitter:image']), sourceUrl),
      prep_minutes: null,
      cook_minutes: null,
      servings: parseYield(micro.yieldText) ?? 4,
      source_url: sourceUrl,
      tags: [],
      ingredients: micro.ingredients.map(parseIngredientLine),
      instructions: dedupeInOrder(micro.instructions),
      method: 'microdata',
    };
  }

  // Metadata-only fallback: at least give them the title and photo.
  const ogTitle = metaContent(html, ['og:title', 'twitter:title']);
  const docTitle = stripTags(html.match(/<title[^>]*>([\s\S]*?)<\/title>/i)?.[1] ?? '');
  if (ogTitle || docTitle) {
    return {
      title: ogTitle ?? docTitle,
      description: metaContent(html, ['og:description', 'description']),
      photo_url: absolutize(metaContent(html, ['og:image', 'twitter:image']), sourceUrl),
      prep_minutes: null,
      cook_minutes: null,
      servings: 4,
      source_url: sourceUrl,
      tags: [],
      ingredients: [],
      instructions: [],
      method: 'metadata',
    };
  }

  return {
    title: 'Imported recipe',
    description: null,
    photo_url: null,
    prep_minutes: null,
    cook_minutes: null,
    servings: 4,
    source_url: sourceUrl,
    tags: [],
    ingredients: [],
    instructions: [],
    method: 'none',
  };
}

function dedupeInOrder(items: string[]): string[] {
  const seen = new Set<string>();
  const out: string[] = [];
  for (const item of items) {
    const key = item.toLowerCase();
    if (seen.has(key)) continue;
    seen.add(key);
    out.push(item);
  }
  return out;
}
