// Walmart adapter.
//
// Live product search uses the Walmart Affiliate API (Walmart.io).
// Cart creation is only reported when the API confirms a cart id.
//
// Required env for live mode:
//   WALMART_CONSUMER_ID       (WM_CONSUMER.ID)
//   WALMART_PRIVATE_KEY       (WM_CONSUMER.SIGNATURE / private key)
// Optional:
//   WALMART_ACCESS_TOKEN      skip token exchange and use this token directly
//   WALMART_API_BASE          default: https://developer.api.walmart.com
//
// Without credentials the adapter is "unconfigured" and the UI uses honest
// Walmart search links instead (no cart is ever claimed).

import type {
  CartResult,
  ProductSearchResult,
  RetailerAdapter,
  RetailerProduct,
  ShoppingListItem,
} from './types';
import { bestMatch, searchQueryForItem } from './match';

const DEFAULT_BASE = 'https://developer.api.walmart.com';

function env(name: string): string | undefined {
  const value = process.env[name];
  return value && value.trim() ? value.trim() : undefined;
}

export function walmartSearchUrl(query: string): string {
  return `https://www.walmart.com/search?q=${encodeURIComponent(query)}`;
}

interface WalmartItem {
  itemId?: number | string;
  name?: string;
  brandName?: string;
  salePrice?: number;
  msrp?: number;
  shortDescription?: string;
  largeImage?: string;
  mediumImage?: string;
  thumbnailImage?: string;
  productUrl?: string;
  canonicalUrl?: string;
  size?: string;
  customerRating?: string;
}

function mapItem(item: WalmartItem): RetailerProduct | null {
  const id = item.itemId != null ? String(item.itemId) : null;
  if (!id || !item.name) return null;
  const price = typeof item.salePrice === 'number' ? item.salePrice : null;
  const url =
    item.productUrl ??
    item.canonicalUrl ??
    `https://www.walmart.com/ip/${id}`;
  return {
    id,
    title: item.name,
    brand: item.brandName ?? null,
    size: item.size ?? null,
    price,
    priceText: price != null ? `$${price.toFixed(2)}` : null,
    imageUrl: item.largeImage ?? item.mediumImage ?? item.thumbnailImage ?? null,
    url,
  };
}

export class WalmartAdapter implements RetailerAdapter {
  id = 'walmart' as const;
  displayName = 'Walmart';

  private cachedToken: { value: string; expiresAt: number } | null = null;

  get isConfigured(): boolean {
    if (env('WALMART_ACCESS_TOKEN')) return true;
    return Boolean(env('WALMART_CONSUMER_ID') && env('WALMART_PRIVATE_KEY'));
  }

  private get base(): string {
    return env('WALMART_API_BASE') ?? DEFAULT_BASE;
  }

  private async getToken(): Promise<string> {
    const direct = env('WALMART_ACCESS_TOKEN');
    if (direct) return direct;

    if (this.cachedToken && this.cachedToken.expiresAt > Date.now() + 30_000) {
      return this.cachedToken.value;
    }

    const consumerId = env('WALMART_CONSUMER_ID');
    const privateKey = env('WALMART_PRIVATE_KEY');
    if (!consumerId || !privateKey) {
      throw new Error('Walmart credentials are not configured.');
    }

    const res = await fetch(`${this.base}/api-proxy/service/affiliate/v2/token`, {
      method: 'POST',
      headers: {
        'WM_CONSUMER.ID': consumerId,
        'WM_CONSUMER.SIGNATURE': privateKey,
        'WM_QOS.CORRELATION_ID': crypto.randomUUID(),
        accept: 'application/json',
      },
    });

    if (!res.ok) {
      throw new Error(`Walmart token request failed (${res.status}).`);
    }
    const json = (await res.json()) as { access_token?: string; expires_in?: number };
    if (!json.access_token) {
      throw new Error('Walmart token response did not include an access token.');
    }
    this.cachedToken = {
      value: json.access_token,
      expiresAt: Date.now() + (json.expires_in ?? 600) * 1000,
    };
    return json.access_token;
  }

  async searchProducts(query: string, limit = 10): Promise<ProductSearchResult> {
    if (!this.isConfigured) {
      return {
        retailer: this.id,
        status: 'unconfigured',
        products: [],
        message: 'Walmart Affiliate API credentials are not configured.',
      };
    }
    try {
      const token = await this.getToken();
      const url = `${this.base}/api-proxy/service/affiliate/v2/items/search?query=${encodeURIComponent(
        query
      )}&numItems=${limit}`;
      const res = await fetch(url, {
        headers: {
          'WM_SEC.ACCESS_TOKEN': token,
          'WM_QOS.CORRELATION_ID': crypto.randomUUID(),
          accept: 'application/json',
        },
      });
      if (!res.ok) {
        return {
          retailer: this.id,
          status: 'error',
          products: [],
          message: `Walmart search failed (${res.status} ${res.statusText}).`,
        };
      }
      const json = (await res.json()) as { items?: WalmartItem[] };
      const products = (json.items ?? [])
        .map(mapItem)
        .filter((p): p is RetailerProduct => p !== null);
      return { retailer: this.id, status: 'ok', products };
    } catch (err) {
      return {
        retailer: this.id,
        status: 'error',
        products: [],
        message: err instanceof Error ? err.message : 'Walmart search failed.',
      };
    }
  }

  async createCart(items: ShoppingListItem[]): Promise<CartResult> {
    // The Walmart Affiliate API does not expose a general cart-creation
    // endpoint for all partners. We only create a cart when a configured
    // endpoint confirms it; otherwise we return honest search links.
    const cartEndpoint = env('WALMART_CART_ENDPOINT');

    if (!this.isConfigured || !cartEndpoint) {
      return {
        retailer: this.id,
        status: 'link',
        message:
          'Direct Walmart cart creation is not available with the current configuration. ' +
          'Use the per-item search links below to shop manually.',
        items: items.map((item) => {
          const query = searchQueryForItem(item);
          return {
            item,
            query,
            product: null,
            confidence: 0,
            searchUrl: walmartSearchUrl(query),
          };
        }),
      };
    }

    try {
      const token = await this.getToken();
      const matched = await Promise.all(
        items.map(async (item) => {
          const query = searchQueryForItem(item);
          const search = await this.searchProducts(query, 8);
          const { product, confidence } =
            search.status === 'ok' ? bestMatch(item, search.products) : { product: null, confidence: 0 };
          return { item, query, product, confidence, searchUrl: walmartSearchUrl(query) };
        })
      );

      const productIds = matched
        .map((m) => m.product?.id)
        .filter((id): id is string => Boolean(id));

      if (productIds.length === 0) {
        return {
          retailer: this.id,
          status: 'link',
          message: 'No matching products found; use the search links to shop manually.',
          items: matched,
        };
      }

      const res = await fetch(cartEndpoint, {
        method: 'POST',
        headers: {
          'WM_SEC.ACCESS_TOKEN': token,
          'WM_QOS.CORRELATION_ID': crypto.randomUUID(),
          'content-type': 'application/json',
          accept: 'application/json',
        },
        body: JSON.stringify({ items: productIds.map((id) => ({ itemId: id, quantity: 1 })) }),
      });

      if (!res.ok) {
        return {
          retailer: this.id,
          status: 'error',
          message: `Walmart cart creation failed (${res.status}). Shop manually with the links below.`,
          items: matched,
        };
      }

      const json = (await res.json()) as { cartId?: string; url?: string };
      if (!json.cartId) {
        return {
          retailer: this.id,
          status: 'error',
          message: 'Walmart did not return a cart id, so no cart was created.',
          items: matched,
        };
      }
      return {
        retailer: this.id,
        status: 'created',
        cartId: json.cartId,
        url: json.url,
        message: 'Walmart cart created.',
        items: matched,
      };
    } catch (err) {
      return {
        retailer: this.id,
        status: 'error',
        message: err instanceof Error ? err.message : 'Walmart cart creation failed.',
        items: items.map((item) => {
          const query = searchQueryForItem(item);
          return { item, query, product: null, confidence: 0, searchUrl: walmartSearchUrl(query) };
        }),
      };
    }
  }
}
