// The password lives in sandbox/cloudflare/.env. The Worker only ever holds its SHA-256 hash.

export async function sha256Hex(value: string): Promise<string> {
  const digest = await crypto.subtle.digest("SHA-256", new TextEncoder().encode(value));
  return [...new Uint8Array(digest)].map((byte) => byte.toString(16).padStart(2, "0")).join("");
}

export async function verifyPassword(given: string, expectedHash: string): Promise<boolean> {
  if (!given || !expectedHash) return false;
  const hash = await sha256Hex(given);
  if (hash.length !== expectedHash.length) return false;
  let difference = 0;
  for (let i = 0; i < hash.length; i++) difference |= hash.charCodeAt(i) ^ expectedHash.charCodeAt(i);
  return difference === 0;
}
