'use client';

import { useState } from 'react';
import { btnSecondary } from './ui';

/** Read-only link with copy + native share support. */
export function CopyLink({ url, label = 'Copy link' }: { url: string; label?: string }) {
  const [copied, setCopied] = useState(false);

  async function copy() {
    try {
      await navigator.clipboard.writeText(url);
      setCopied(true);
      setTimeout(() => setCopied(false), 2000);
    } catch {
      setCopied(false);
    }
  }

  async function share() {
    if (typeof navigator !== 'undefined' && 'share' in navigator) {
      try {
        await navigator.share({ url, title: 'Vote on meals' });
      } catch {
        // user cancelled
      }
    } else {
      await copy();
    }
  }

  return (
    <div className="flex flex-wrap items-center gap-2">
      <input
        readOnly
        value={url}
        onFocus={(e) => e.currentTarget.select()}
        className="min-w-0 flex-1 rounded-xl border border-sand-dark bg-sand/50 px-3 py-2 text-xs text-ink-soft"
      />
      <button type="button" onClick={copy} className={btnSecondary}>
        {copied ? 'Copied!' : label}
      </button>
      <button type="button" onClick={share} className={btnSecondary}>
        Share
      </button>
    </div>
  );
}
