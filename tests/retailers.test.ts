import { afterEach, describe, expect, it, vi } from 'vitest';
import { WalmartAdapter, walmartSearchUrl } from '@/lib/retailers/walmart';
import { InstacartAdapter, instacartSearchUrl } from '@/lib/retailers/instacart';
import { bestMatch, similarity } from '@/lib/retailers/match';
import { assertPublicUrl, safeFetchHtml } from '@/lib/import/safe-fetch';

const ITEM = { id: 'i1', name: 'olive oil', qty: 3, unit: 'tbsp' };

const originalEnv = { ...process.env };

afterEach(() => {
  process.env = { ...originalEnv };
  vi.restoreAllMocks();
  vi.unstubAllGlobals();
});

describe('retailer fallback links', () => {
  it('builds honest search links', () => {
    expect(walmartSearchUrl('olive oil')).toBe('https://www.walmart.com/search?q=olive%20oil');
    expect(instacartSearchUrl('olive oil')).toBe('https://www.instacart.com/store/s?k=olive%20oil');
  });
});

describe('unconfigured adapters', () => {
  it('reports unconfigured rather than faking products', async () => {
    delete process.env.WALMART_ACCESS_TOKEN;
    delete process.env.WALMART_CONSUMER_ID;
    delete process.env.INSTACART_API_KEY;

    const walmart = new WalmartAdapter();
    const instacart = new InstacartAdapter();
    expect(walmart.isConfigured).toBe(false);
    expect(instacart.isConfigured).toBe(false);

    const wResult = await walmart.searchProducts('milk');
    expect(wResult.status).toBe('unconfigured');
    expect(wResult.products).toHaveLength(0);

    const cart = await walmart.createCart([ITEM]);
    expect(cart.status).toBe('link');
    expect(cart.cartId).toBeUndefined();
    expect(cart.items[0].searchUrl).toContain('walmart.com/search');
  });

  it('never claims a cart when the API fails', async () => {
    process.env.WALMART_ACCESS_TOKEN = 'fake-token';
    process.env.WALMART_CART_ENDPOINT = 'https://developer.api.walmart.com/carts';

    const fetchMock = vi.fn(async (input: RequestInfo | URL) => {
      const url = String(input);
      if (url.includes('/items/search')) {
        return new Response(JSON.stringify({ items: [] }), { status: 200 });
      }
      return new Response('nope', { status: 500 });
    });
    vi.stubGlobal('fetch', fetchMock);

    const walmart = new WalmartAdapter();
    expect(walmart.isConfigured).toBe(true);
    const cart = await walmart.createCart([ITEM]);
    expect(cart.status).toBe('link');
    expect(cart.cartId).toBeUndefined();
  });

  it('returns real products when the Walmart API succeeds', async () => {
    process.env.WALMART_ACCESS_TOKEN = 'fake-token';
    const fetchMock = vi.fn(async () =>
      new Response(
        JSON.stringify({
          items: [
            {
              itemId: 123,
              name: 'Great Value Olive Oil, 16.9 fl oz',
              brandName: 'Great Value',
              salePrice: 7.98,
              productUrl: 'https://www.walmart.com/ip/123',
            },
          ],
        }),
        { status: 200 }
      )
    );
    vi.stubGlobal('fetch', fetchMock);

    const walmart = new WalmartAdapter();
    const result = await walmart.searchProducts('olive oil');
    expect(result.status).toBe('ok');
    expect(result.products).toHaveLength(1);
    expect(result.products[0].priceText).toBe('$7.98');
  });

  it('only reports a cart as created when the API returns a cart id', async () => {
    process.env.WALMART_ACCESS_TOKEN = 'fake-token';
    process.env.WALMART_CART_ENDPOINT = 'https://developer.api.walmart.com/carts';
    const fetchMock = vi.fn(async (input: RequestInfo | URL) => {
      const url = String(input);
      if (url.includes('/items/search')) {
        return new Response(
          JSON.stringify({ items: [{ itemId: 1, name: 'Olive Oil 16oz', salePrice: 5 }] }),
          { status: 200 }
        );
      }
      return new Response(JSON.stringify({ cartId: 'cart-42', url: 'https://walmart.com/cart' }), {
        status: 200,
      });
    });
    vi.stubGlobal('fetch', fetchMock);

    const cart = await new WalmartAdapter().createCart([ITEM]);
    expect(cart.status).toBe('created');
    expect(cart.cartId).toBe('cart-42');
  });

  it('surfaces Instacart API errors instead of faking success', async () => {
    process.env.INSTACART_API_KEY = 'fake-key';
    vi.stubGlobal(
      'fetch',
      vi.fn(async () => new Response('unauthorized', { status: 401 }))
    );
    const result = await new InstacartAdapter().searchProducts('milk');
    expect(result.status).toBe('error');
    expect(result.message).toContain('401');
  });
});

describe('product matching', () => {
  it('scores related titles higher', () => {
    const products = [
      { id: 'a', title: 'Barilla Spaghetti 16oz', brand: null, size: null, price: null, priceText: null, imageUrl: null, url: '' },
      { id: 'b', title: 'Great Value Whole Milk 1 Gallon', brand: null, size: null, price: null, priceText: null, imageUrl: null, url: '' },
    ];
    const { product, confidence } = bestMatch({ id: 'i', name: 'milk', qty: 1, unit: 'gallon' }, products);
    expect(product?.id).toBe('b');
    expect(confidence).toBeGreaterThan(0.25);
    expect(similarity('milk', 'spaghetti')).toBe(0);
  });
});

describe('SSRF protection', () => {
  it('rejects non-http protocols and private hosts', async () => {
    await expect(assertPublicUrl('file:///etc/passwd')).rejects.toThrow();
    await expect(assertPublicUrl('http://localhost/admin')).rejects.toThrow();
    await expect(assertPublicUrl('http://127.0.0.1/')).rejects.toThrow();
    await expect(assertPublicUrl('http://192.168.1.1/')).rejects.toThrow();
    await expect(assertPublicUrl('http://169.254.169.254/latest/meta-data')).rejects.toThrow();
    await expect(assertPublicUrl('http://[::1]/')).rejects.toThrow();
  });

  it('allows a public https URL', async () => {
    const url = await assertPublicUrl('https://example.com/recipe');
    expect(url.hostname).toBe('example.com');
  });

  it('does not fetch blocked hosts', async () => {
    const spy = vi.fn();
    vi.stubGlobal('fetch', spy);
    await expect(safeFetchHtml('http://169.254.169.254/')).rejects.toThrow();
    expect(spy).not.toHaveBeenCalled();
  });
});
