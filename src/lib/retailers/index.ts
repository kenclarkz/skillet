// Retailer registry + shopping orchestration.

import { WalmartAdapter } from './walmart';
import { InstacartAdapter } from './instacart';
import type { CartResult, RetailerAdapter, RetailerId, ShoppingListItem } from './types';

export const walmart = new WalmartAdapter();
export const instacart = new InstacartAdapter();

export const retailers: Record<RetailerId, RetailerAdapter> = {
  walmart,
  instacart,
};

export function getRetailer(id: string): RetailerAdapter | null {
  if (id === 'walmart' || id === 'instacart') return retailers[id];
  return null;
}

export function retailerStatus() {
  return (Object.keys(retailers) as RetailerId[]).map((id) => ({
    id,
    displayName: retailers[id].displayName,
    configured: retailers[id].isConfigured,
  }));
}

/** Send the list to a retailer, degrading honestly to manual links. */
export async function shopWithRetailer(
  id: RetailerId,
  items: ShoppingListItem[]
): Promise<CartResult> {
  const adapter = retailers[id];
  return adapter.createCart(items);
}

export * from './types';
export { walmartSearchUrl } from './walmart';
export { instacartSearchUrl } from './instacart';
