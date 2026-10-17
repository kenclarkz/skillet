// SSRF-safe fetch for user-supplied recipe URLs.
import { lookup } from 'node:dns/promises';
import net from 'node:net';

const BLOCKED_HOSTNAMES = new Set([
  'localhost',
  'localhost.localdomain',
  'metadata.google.internal',
]);

const MAX_BYTES = 5 * 1024 * 1024; // 5 MB
const MAX_REDIRECTS = 5;
const TIMEOUT_MS = 12_000;

function isPrivateIPv4(ip: string): boolean {
  const parts = ip.split('.').map((p) => parseInt(p, 10));
  if (parts.length !== 4 || parts.some((p) => Number.isNaN(p))) return true;
  const [a, b] = parts;
  if (a === 0 || a === 10 || a === 127) return true;
  if (a === 169 && b === 254) return true; // link-local
  if (a === 172 && b >= 16 && b <= 31) return true;
  if (a === 192 && b === 168) return true;
  if (a === 100 && b >= 64 && b <= 127) return true; // CGNAT
  return false;
}

function isPrivateIPv6(ip: string): boolean {
  const addr = ip.toLowerCase().split('%')[0];
  if (addr === '::1' || addr === '::') return true;
  if (addr.startsWith('fc') || addr.startsWith('fd')) return true; // unique local
  if (addr.startsWith('fe80')) return true; // link-local
  const v4 = addr.match(/(\d+\.\d+\.\d+\.\d+)$/);
  if (v4) return isPrivateIPv4(v4[1]);
  return false;
}

/** Throws if the URL is not safe to fetch server-side. */
export async function assertPublicUrl(rawUrl: string): Promise<URL> {
  let url: URL;
  try {
    url = new URL(rawUrl);
  } catch {
    throw new Error('That does not look like a valid URL.');
  }
  if (url.protocol !== 'http:' && url.protocol !== 'https:') {
    throw new Error('Only http and https URLs are supported.');
  }
  const hostname = url.hostname.toLowerCase().replace(/^\[|\]$/g, '');
  if (BLOCKED_HOSTNAMES.has(hostname) || hostname.endsWith('.local') || hostname.endsWith('.internal')) {
    throw new Error('That host is not allowed.');
  }
  if (net.isIP(hostname)) {
    if ((net.isIPv4(hostname) && isPrivateIPv4(hostname)) || (net.isIPv6(hostname) && isPrivateIPv6(hostname))) {
      throw new Error('Private network addresses are not allowed.');
    }
    return url;
  }
  let addresses: { address: string }[];
  try {
    addresses = await lookup(hostname, { all: true });
  } catch {
    throw new Error(`Could not resolve ${hostname}.`);
  }
  for (const { address } of addresses) {
    if (net.isIPv4(address) ? isPrivateIPv4(address) : isPrivateIPv6(address)) {
      throw new Error('Private network addresses are not allowed.');
    }
  }
  return url;
}

/** Fetch a remote HTML page with size, redirect, and SSRF protections. */
export async function safeFetchHtml(rawUrl: string): Promise<{ html: string; finalUrl: string }> {
  let current = await assertPublicUrl(rawUrl);

  for (let i = 0; i <= MAX_REDIRECTS; i++) {
    const controller = new AbortController();
    const timer = setTimeout(() => controller.abort(), TIMEOUT_MS);
    let response: Response;
    try {
      response = await fetch(current, {
        redirect: 'manual',
        signal: controller.signal,
        headers: {
          'user-agent':
            'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122 Safari/537.36',
          accept: 'text/html,application/xhtml+xml',
          'accept-language': 'en-US,en;q=0.9',
        },
      });
    } catch (err) {
      clearTimeout(timer);
      if (err instanceof Error && err.name === 'AbortError') {
        throw new Error('The site took too long to respond.');
      }
      throw new Error('Could not reach that website.');
    }
    clearTimeout(timer);

    if (response.status >= 300 && response.status < 400) {
      const location = response.headers.get('location');
      if (!location) throw new Error('The site returned an invalid redirect.');
      current = await assertPublicUrl(new URL(location, current).toString());
      continue;
    }

    if (!response.ok) {
      throw new Error(`The site responded with ${response.status}.`);
    }

    const contentType = response.headers.get('content-type') ?? '';
    if (!contentType.includes('html') && !contentType.includes('xml') && contentType !== '') {
      throw new Error('That URL is not an HTML page.');
    }

    const reader = response.body?.getReader();
    if (!reader) throw new Error('Empty response from the site.');
    const chunks: Uint8Array[] = [];
    let total = 0;
    for (;;) {
      const { done, value } = await reader.read();
      if (done) break;
      total += value.byteLength;
      if (total > MAX_BYTES) {
        await reader.cancel();
        throw new Error('That page is too large to import.');
      }
      chunks.push(value);
    }
    const buffer = Buffer.concat(chunks.map((c) => Buffer.from(c)));
    const charsetMatch = contentType.match(/charset=([\w-]+)/i);
    const charset = (charsetMatch?.[1] ?? 'utf-8').toLowerCase();
    const html = new TextDecoder(charset === 'iso-8859-1' ? 'latin1' : charset).decode(buffer);
    return { html, finalUrl: current.toString() };
  }

  throw new Error('Too many redirects.');
}
