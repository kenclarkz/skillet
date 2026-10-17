// Instacart adapter.
//
// Live mode uses the Instacart Connect / Developer Platform partner API.
// Partner APIs require approved credentials and their paths vary between
// programs, so the base URL and paths are configurable and every failure is
// surfaced honestly. We never claim a cart exists unless Instacart returned
// a cart id.
//
// Required env for live mode:
//   INSTACART_API_KEY         (Bearer token / API key)
// Optional:
//   INSTACART_API_BASE        default: https://api.instacart.com/v2
//   INSTACART_CART_PATH       default: /carts
//   INSTACART_SEARCH_PATH     default: /products
//
// Without credentials the adapter is "unconfigured"; the UI then provides
// honest Instacart search links and a manual checklist.

import type {
  CartResult,
  ProductSearchResult,
  RetailerAdapter,
  RetailerProduct,
  ShoppingListItem,
} from './types';
import { bestMatch, searchQueryForItem } from './match';

const DEFAULT_BASE = 'https://api.instacart.com/v2';

function env(name: string): string | undefined {
  const value = process.env[name];
  return value && value.trim() ? value.trim() : undefined;
}

export function instacartSearchUrl(query: string): string {
  return `https://www.instacart.com/store/s?k=${encodeURIComponent(query)}`;
}

interface InstacartProduct {
  id?: string | number;
  product_id?: string | number;
  name?: string;
  title?: string;
  brand?: string;
  brand_name?: string;
  size?: string;
  price?: number;
  image_url?: string;
  image?: string;
  url?: string;
  permalink?: string;
}

function mapProduct(p: InstacartProduct): RetailerProduct | null {
  const id = p.id ?? p.product_id;
  const title = p.name ?? p.title;
  if (id == null || !title) return null;
  const price = typeof p.price === 'number' ? p.price : null;
  return {
    id: String(id),
    title,
    brand: p.brand ?? p.brand_name ?? null,
    size: p.size ?? null,
    price,
    priceText: price != null ? `$${price.toFixed(2)}` : null,
    imageUrl: p.image_url ?? p.image ?? null,
    url: p.url ?? p.permalink ?? `https://www.instacart.com/products/${id}`,
  };
}

export class InstacartAdapter implements RetailerAdapter {
  id = 'instacart' as const;
  displayName = 'Instacart';

  get isConfigured(): boolean {
    return Boolean(env('INSTACART_API_KEY'));
  }

  private get base(): string {
    return (env('INSTACART_API_BASE') ?? DEFAULT_BASE).replace(/\/$/, '');
  }

  private headers(): Record<string, string> {
    return {
      authorization: `Bearer ${env('INSTACART_API_KEY')}`,
      accept: 'application/json',
    };
  }

  async searchProducts(query: string, limit = 10): Promise<ProductSearchResult> {
    if (!this.isConfigured) {
      return {
        retailer: this.id,
        status: 'unconfigured',
        products: [],
        message: 'Instacart partner API credentials are not configured.',
      };
    }
    try {
      const path = env('INSTACART_SEARCH_PATH') ?? '/products';
      const res = await fetch(
        `${this.base}${path}?q=${encodeURIComponent(query)}&limit=${limit}`,
        { headers: this.headers() }
      );
      if (!res.ok) {
        return {
          retailer: this.id,
          status: 'error',
          products: [],
          message: `Instacart search failed (${res.status} ${res.statusText}).`,
        };
      }
      const json = (await res.json()) as { products?: InstacartProduct[]; data?: InstacartProduct[] };
      const raw = json.products ?? json.data ?? [];
      const products = raw.map(mapProduct).filter((p): p is RetailerProduct => p !== null);
      return { retailer: this.id, status: 'ok', products };
    } catch (err) {
      return {
        retailer: this.id,
        status: 'error',
        products: [],
        message: err instanceof Error ? err.message : 'Instacart search failed.',
      };
    }
  }

  async createCart(items: ShoppingListItem[]): Promise<CartResult> {
    if (!this.isConfigured) {
      return {
        retailer: this.id,
        status: 'link',
        message:
          'Instacart partner API credentials are not configured. Use the search links to shop manually.',
        items: items.map((item) => {
          const query = searchQueryForItem(item);
          return { item, query, product: null, confidence: 0, searchUrl: instacartSearchUrl(query) };
        }),
      };
    }

    try {
      const matched = await Promise.all(
        items.map(async (item) => {
          const query = searchQueryForItem(item);
          const search = await this.searchProducts(query, 8);
          const { product, confidence } =
            search.status === 'ok' ? bestMatch(item, search.products) : { product: null, confidence: 0 };
          return { item, query, product, confidence, searchUrl: instacartSearchUrl(query) };
        })
      );

      const lineItems = matched
        .filter((m) => m.product)
        .map((m) => ({ product_id: m.product!.id, quantity: 1 }));

      if (lineItems.length === 0) {
        return {
          retailer: this.id,
          status: 'link',
          message: 'No matching products found; use the search links to shop manually.',
          items: matched,
        };
      }

      const path = env('INSTACART_CART_PATH') ?? '/carts';
      const res = await fetch(`${this.base}${path}`, {
        method: 'POST',
        headers: { ...this.headers(), 'content-type': 'application/json' },
        body: JSON.stringify({ line_items: lineItems }),
      });

      if (!res.ok) {
        return {
          retailer: this.id,
          status: 'error',
          message: `Instacart cart creation failed (${res.status}). Shop manually with the links below.`,
          items: matched,
        };
      }

      const json = (await res.json()) as { cart_id?: string; id?: string; products_link_url?: string; url?: string };
      const cartId = json.cart_id ?? json.id;
      if (!cartId) {
        return {
          retailer: this.id,
          status: 'error',
          message: 'Instacart did not return a cart id, so no cart was created.',
          items: matched,
        };
      }
      return {
        retailer: this.id,
        status: 'created',
        cartId,
        url: json.products_link_url ?? json.url,
        message: 'Instacart cart created.',
        items: matched,
      };
    } catch (err) {
      return {
        retailer: this.id,
        status: 'error',
        message: err instanceof Error ? err.message : 'Instacart cart creation failed.',
        items: items.map((item) => {
          const query = searchQueryForItem(item);
          return { item, query, product: null, confidence: 0, searchUrl: instacartSearchUrl(query) };
        }),
      };
    }
  }
}
