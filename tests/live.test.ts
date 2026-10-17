import { describe, expect, it } from 'vitest';
import { assertPublicUrl, safeFetchHtml } from '@/lib/import/safe-fetch';
import { parseRecipeHtml } from '@/lib/import/parse';

// These tests hit the real internet. Set SKIP_LIVE=1 to skip them in offline CI.
const live = process.env.SKIP_LIVE === '1' ? describe.skip : describe;

live('live recipe import', () => {
  it('fetches a public HTML page', async () => {
    const { html } = await safeFetchHtml('https://example.com');
    expect(html.toLowerCase()).toContain('<html');
  });

  it('blocks private/loopback hosts', async () => {
    await expect(assertPublicUrl('http://127.0.0.1/recipe')).rejects.toThrow();
    await expect(assertPublicUrl('http://169.254.169.254/latest/meta-data')).rejects.toThrow();
    await expect(assertPublicUrl('http://localhost:3000')).rejects.toThrow();
  });

  it('imports a real recipe page into a structured draft', async () => {
    const url = 'https://www.bbcgoodfood.com/recipes/classic-lasagne';
    const { html, finalUrl } = await safeFetchHtml(url);
    const draft = parseRecipeHtml(html, finalUrl);

    expect(draft.title.length).toBeGreaterThan(2);
    expect(draft.ingredients.length).toBeGreaterThan(2);
    expect(draft.instructions.length).toBeGreaterThan(0);
    expect(draft.source_url).toBe(finalUrl);
  });

  it('imports a second real recipe site', async () => {
    const url = 'https://www.skinnytaste.com/baked-chicken-breast/';
    const { html, finalUrl } = await safeFetchHtml(url);
    const draft = parseRecipeHtml(html, finalUrl);

    expect(draft.title.toLowerCase()).toContain('chicken');
    expect(draft.ingredients.length).toBeGreaterThan(2);
  });
});
