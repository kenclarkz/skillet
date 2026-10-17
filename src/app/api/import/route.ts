import { NextResponse, type NextRequest } from 'next/server';
import { safeFetchHtml } from '@/lib/import/safe-fetch';
import { parseRecipeHtml } from '@/lib/import/parse';
import { createClient } from '@/lib/supabase/server';

export const runtime = 'nodejs';
export const dynamic = 'force-dynamic';

export async function POST(request: NextRequest) {
  const supabase = await createClient();
  const {
    data: { user },
  } = await supabase.auth.getUser();
  if (!user) {
    return NextResponse.json({ error: 'Sign in to import recipes.' }, { status: 401 });
  }

  let url: string | undefined;
  try {
    const body = (await request.json()) as { url?: string };
    url = body.url?.trim();
  } catch {
    return NextResponse.json({ error: 'Invalid request body.' }, { status: 400 });
  }

  if (!url) {
    return NextResponse.json({ error: 'Paste a recipe URL first.' }, { status: 400 });
  }

  try {
    const { html, finalUrl } = await safeFetchHtml(url);
    const draft = parseRecipeHtml(html, finalUrl);

    if (draft.method === 'none') {
      return NextResponse.json(
        {
          error:
            'We could not find recipe details on that page. It may be behind a login or rely on JavaScript. You can still add it manually.',
          draft,
        },
        { status: 422 }
      );
    }

    return NextResponse.json({ draft });
  } catch (err) {
    return NextResponse.json(
      { error: err instanceof Error ? err.message : 'Import failed.' },
      { status: 400 }
    );
  }
}
