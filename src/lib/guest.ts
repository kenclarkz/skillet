// Guest identity helpers for QR-code voting. Guests have no account, so we
// mint a stable per-device key that is stored locally and sent with each vote.

export const GUEST_KEY_STORAGE = 'skillet_guest_key';
export const GUEST_NAME_STORAGE = 'skillet_guest_name';

/** Create a new opaque guest voter key, always prefixed to match RLS rules. */
export function generateVoterKey(random: () => string = defaultRandom): string {
  return `guest:${random()}`;
}

function defaultRandom(): string {
  if (typeof globalThis.crypto?.randomUUID === 'function') {
    return globalThis.crypto.randomUUID();
  }
  return `${Date.now().toString(36)}${Math.random().toString(36).slice(2, 10)}`;
}
