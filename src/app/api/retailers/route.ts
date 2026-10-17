import { NextResponse } from 'next/server';
import { retailerStatus } from '@/lib/retailers';

export const dynamic = 'force-dynamic';

export async function GET() {
  return NextResponse.json({ retailers: retailerStatus() });
}
