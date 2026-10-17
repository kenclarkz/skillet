import { NextResponse, type NextRequest } from 'next/server';
import { createClient } from '@/lib/supabase/server';
import { formatQuantity } from '@/lib/grocery/aggregate';
import { getRetailer } from '@/lib/retailers';
import type { ShoppingListItem } from '@/lib/retailers/types';

export const runtime = 'nodejs';
export const dynamic = 'force-dynamic';

export async function POST(request: NextRequest) {
  const supabase = await createClient();
  const {
    data: { user },
  } = await supabase.auth.getUser();
  if (!user) {
    return NextResponse.json({ error: 'Sign in required.' }, { status: 401 });
  }

  let retailerId: string | undefined;
  let planId: string | undefined;
  try {
    const body = (await request.json()) as { retailer?: string; planId?: string };
    retailerId = body.retailer;
    planId = body.planId;
  } catch {
    return NextResponse.json({ error: 'Invalid request.' }, { status: 400 });
  }

  const retailer = retailerId ? getRetailer(retailerId) : null;
  if (!retailer || !planId) {
    return NextResponse.json({ error: 'Unknown retailer or missing plan.' }, { status: 400 });
  }

  const { data: plan } = await supabase
    .from('weekly_plans')
    .select('id, cookbook_id')
    .eq('id', planId)
    .maybeSingle();
  if (!plan) {
    return NextResponse.json({ error: 'Plan not found.' }, { status: 404 });
  }

  const { data: list } = await supabase
    .from('grocery_lists')
    .select('id')
    .eq('plan_id', planId)
    .maybeSingle();

  let items: ShoppingListItem[] = [];
  if (list?.id) {
    const { data: rows } = await supabase
      .from('grocery_items')
      .select('id, name, qty, unit, checked, excluded')
      .eq('list_id', list.id)
      .eq('excluded', false)
      .order('sort_key', { ascending: true });

    items = (rows ?? []).map((row) => ({
      id: row.id as string,
      name: row.name as string,
      qty: (row.qty as number | null) ?? null,
      unit: (row.unit as string | null) ?? '',
    }));
  }

  if (items.length === 0) {
    return NextResponse.json(
      { error: 'Build the grocery list first — there is nothing to shop for yet.' },
      { status: 400 }
    );
  }

  // This always performs a real API call (or an honest fallback); failures are
  // reported as-is and never presented as a successful cart.
  const result = await retailer.createCart(items);

  return NextResponse.json({
    result: {
      ...result,
      items: result.items.map((matched) => ({
        ...matched,
        display: formatQuantity({
          qty: matched.item.qty,
          unit: matched.item.unit,
          missing_qty: matched.item.qty === null,
        }),
      })),
    },
  });
}
