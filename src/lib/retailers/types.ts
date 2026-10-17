// Retailer integration contracts.
//
// IMPORTANT: We never report a cart as created unless the retailer API
// confirmed it. When credentials are missing or a call fails, adapters return
// an honest status and the UI falls back to search links + a manual checklist.

export type RetailerId = 'walmart' | 'instacart';

export interface ShoppingListItem {
  id: string;
  name: string;
  qty: number | null;
  unit: string;
}

export interface RetailerProduct {
  id: string;
  title: string;
  brand: string | null;
  size: string | null;
  price: number | null;
  priceText: string | null;
  imageUrl: string | null;
  url: string;
}

export interface ProductSearchResult {
  retailer: RetailerId;
  /** 'ok' = live API data. 'error' = API configured but the call failed. */
  status: 'ok' | 'error' | 'unconfigured';
  products: RetailerProduct[];
  message?: string;
}

export interface MatchedItem {
  item: ShoppingListItem;
  /** The query we searched/opened a link for. */
  query: string;
  product: RetailerProduct | null;
  confidence: number;
  /** Manual fallback link (always available, never a fake cart). */
  searchUrl: string;
}

export interface CartResult {
  retailer: RetailerId;
  /**
   * 'created'  -> retailer confirmed a cart (API response included a cart id)
   * 'link'     -> no direct cart; we can only provide search/product links
   * 'error'    -> API configured but the request failed (see message)
   */
  status: 'created' | 'link' | 'error';
  cartId?: string;
  url?: string;
  message: string;
  items: MatchedItem[];
}

export interface RetailerAdapter {
  id: RetailerId;
  displayName: string;
  /** True when the required credentials are present in env. */
  isConfigured: boolean;
  searchProducts(query: string, limit?: number): Promise<ProductSearchResult>;
  createCart(items: ShoppingListItem[]): Promise<CartResult>;
}
