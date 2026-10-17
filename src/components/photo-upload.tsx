'use client';

import { useRef, useState } from 'react';
import { createClient } from '@/lib/supabase/client';
import { PHOTO_BUCKET } from '@/lib/supabase/env';
import { btnSecondary } from './ui';

/**
 * Uploads a recipe photo to Supabase Storage directly from the browser.
 * The storage path is `${cookbookId}/${uuid}-${filename}` so that the
 * bucket's RLS policies can check cookbook edit rights.
 */
export function PhotoUpload({
  cookbookId,
  initialUrl,
  initialPath,
}: {
  cookbookId: string;
  initialUrl?: string | null;
  initialPath?: string | null;
}) {
  const [preview, setPreview] = useState<string | null>(initialUrl ?? null);
  const [path, setPath] = useState<string>(initialPath ?? '');
  const [status, setStatus] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const inputRef = useRef<HTMLInputElement>(null);

  async function onFile(event: React.ChangeEvent<HTMLInputElement>) {
    const file = event.target.files?.[0];
    if (!file) return;
    setError(null);
    setStatus('Uploading…');
    try {
      const supabase = createClient();
      const safeName = file.name.replace(/[^a-zA-Z0-9._-]/g, '-').slice(-60);
      const objectPath = `${cookbookId}/${crypto.randomUUID()}-${safeName}`;
      const { error: uploadError } = await supabase.storage
        .from(PHOTO_BUCKET)
        .upload(objectPath, file, { cacheControl: '3600', upsert: false, contentType: file.type });
      if (uploadError) throw uploadError;

      const { data } = supabase.storage.from(PHOTO_BUCKET).getPublicUrl(objectPath);
      setPath(objectPath);
      setPreview(data.publicUrl);
      setStatus('Photo uploaded');
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Upload failed.');
      setStatus(null);
    }
  }

  return (
    <div className="space-y-2">
      <input type="hidden" name="photo_path" value={path} />
      <div className="flex items-start gap-3">
        <div className="h-24 w-24 shrink-0 overflow-hidden rounded-xl border border-sand-dark bg-sand">
          {preview ? (
            // eslint-disable-next-line @next/next/no-img-element
            <img src={preview} alt="Recipe photo preview" className="h-full w-full object-cover" />
          ) : (
            <div className="flex h-full w-full items-center justify-center text-2xl" aria-hidden>
              🍽️
            </div>
          )}
        </div>
        <div className="space-y-2">
          <button
            type="button"
            className={btnSecondary}
            onClick={() => inputRef.current?.click()}
          >
            {preview ? 'Replace photo' : 'Add a photo'}
          </button>
          <input
            ref={inputRef}
            type="file"
            accept="image/*"
            className="hidden"
            onChange={onFile}
          />
          {cookbookId ? null : (
            <p className="text-xs text-ink-soft">Save the cookbook first to add photos.</p>
          )}
          {status ? <p className="text-xs text-olive-dark">{status}</p> : null}
          {error ? <p className="text-xs text-terracotta-dark">{error}</p> : null}
          <p className="text-xs text-ink-soft">JPG or PNG, up to ~5 MB.</p>
        </div>
      </div>
    </div>
  );
}
