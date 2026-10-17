import { describe, expect, it } from 'vitest';
import { parseIsoDuration, parseRecipeHtml, parseYield } from '@/lib/import/parse';

const JSON_LD_HTML = `<!doctype html><html><head>
<title>Site name</title>
<script type="application/ld+json">
{
  "@context": "https://schema.org",
  "@type": "Recipe",
  "name": "Weeknight Chili",
  "description": "A fast, smoky chili.",
  "image": ["https://example.com/chili.jpg"],
  "prepTime": "PT15M",
  "cookTime": "PT45M",
  "recipeYield": "6 servings",
  "recipeCategory": "Dinner",
  "keywords": "chili, easy",
  "recipeIngredient": [
    "2 tbsp olive oil",
    "1 lb ground beef",
    "2 (14 oz) cans diced tomatoes",
    "Salt to taste"
  ],
  "recipeInstructions": [
    {"@type": "HowToStep", "text": "Heat the oil."},
    {"@type": "HowToStep", "text": "Brown the beef."},
    {"@type": "HowToSection", "name": "Finish", "itemListElement": [
      {"@type": "HowToStep", "text": "Simmer for 30 minutes."}
    ]}
  ]
}
</script></head><body></body></html>`;

const GRAPH_HTML = `<html><head><script type="application/ld+json">
{"@context":"https://schema.org","@graph":[
 {"@type":"WebSite","name":"Blog"},
 {"@type":"Recipe","name":"Graph Tacos","recipeIngredient":["1 onion"],"recipeInstructions":"Dice and cook."}
]}
</script></head></html>`;

const MICRODATA_HTML = `<html><head><title>Microdata Soup</title>
<meta property="og:image" content="/images/soup.jpg" />
</head><body itemscope itemtype="https://schema.org/Recipe">
<h1 itemprop="name">Microdata Soup</h1>
<meta itemprop="recipeYield" content="4 bowls" />
<li itemprop="recipeIngredient">3 cups broth</li>
<li itemprop="recipeIngredient">1 onion</li>
<li itemprop="recipeInstructions">Boil everything.</li>
</body></html>`;

const OG_ONLY_HTML = `<html><head>
<meta property="og:title" content="Mystery Cake" />
<meta property="og:description" content="A cake from a blog." />
<meta property="og:image" content="https://example.com/cake.png" />
</head><body>no structured data</body></html>`;

describe('parseIsoDuration', () => {
  it('parses ISO-8601 durations', () => {
    expect(parseIsoDuration('PT15M')).toBe(15);
    expect(parseIsoDuration('PT1H30M')).toBe(90);
    expect(parseIsoDuration('P1DT2H')).toBe(1560);
    expect(parseIsoDuration('nope')).toBeNull();
  });

  it('parses human-readable durations as a fallback', () => {
    expect(parseIsoDuration('1 hour 15 minutes')).toBe(75);
  });
});

describe('parseYield', () => {
  it('extracts serving counts', () => {
    expect(parseYield('6 servings')).toBe(6);
    expect(parseYield(8)).toBe(8);
    expect(parseYield(['4 bowls'])).toBe(4);
    expect(parseYield('a lot')).toBeNull();
  });
});

describe('parseRecipeHtml', () => {
  it('extracts a full JSON-LD recipe', () => {
    const draft = parseRecipeHtml(JSON_LD_HTML, 'https://example.com/chili');
    expect(draft.method).toBe('json-ld');
    expect(draft.title).toBe('Weeknight Chili');
    expect(draft.photo_url).toBe('https://example.com/chili.jpg');
    expect(draft.prep_minutes).toBe(15);
    expect(draft.cook_minutes).toBe(45);
    expect(draft.servings).toBe(6);
    expect(draft.ingredients).toHaveLength(4);
    expect(draft.ingredients[0]).toMatchObject({ qty: '2', unit: 'tbsp', name: 'olive oil' });
    expect(draft.instructions).toEqual([
      'Heat the oil.',
      'Brown the beef.',
      'Simmer for 30 minutes.',
    ]);
    expect(draft.tags).toContain('Dinner');
  });

  it('walks @graph structures', () => {
    const draft = parseRecipeHtml(GRAPH_HTML, 'https://example.com/tacos');
    expect(draft.method).toBe('json-ld');
    expect(draft.title).toBe('Graph Tacos');
    expect(draft.ingredients).toHaveLength(1);
    expect(draft.instructions).toEqual(['Dice and cook.']);
  });

  it('falls back to microdata with an absolute image URL', () => {
    const draft = parseRecipeHtml(MICRODATA_HTML, 'https://example.com/soup');
    expect(draft.method).toBe('microdata');
    expect(draft.title).toBe('Microdata Soup');
    expect(draft.photo_url).toBe('https://example.com/images/soup.jpg');
    expect(draft.servings).toBe(4);
    expect(draft.ingredients).toHaveLength(2);
  });

  it('falls back to metadata when nothing else exists', () => {
    const draft = parseRecipeHtml(OG_ONLY_HTML, 'https://example.com/cake');
    expect(draft.method).toBe('metadata');
    expect(draft.title).toBe('Mystery Cake');
    expect(draft.ingredients).toHaveLength(0);
  });

  it('does not throw on malformed JSON-LD', () => {
    const draft = parseRecipeHtml(
      `<html><head><title>Bad</title><script type="application/ld+json">{not json}</script></head></html>`,
      'https://example.com/bad'
    );
    expect(draft.method).toBe('metadata');
    expect(draft.title).toBe('Bad');
  });
});
