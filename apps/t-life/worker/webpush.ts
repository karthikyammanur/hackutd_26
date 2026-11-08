/** Web Push with WebCrypto only: RFC 8291 payload encryption and RFC 8292 VAPID. */

type Bytes = Uint8Array<ArrayBuffer>;

export interface PushSubscriptionRecord {
  endpoint: string;
  p256dh: string;
  auth: string;
}

export interface VapidKeys {
  publicKey: string;
  /** The private key as a JSON Web Key string. */
  privateJwk: string;
  subject: string;
}

const text = new TextEncoder();
const RECORD_SIZE = 4096;
const TOKEN_LIFETIME_S = 12 * 60 * 60;

export function fromBase64Url(value: string): Bytes {
  const binary = atob(value.replace(/-/g, "+").replace(/_/g, "/"));
  return Uint8Array.from(binary, (char) => char.charCodeAt(0));
}

export function toBase64Url(bytes: Uint8Array): string {
  return btoa(String.fromCharCode(...bytes)).replace(/\+/g, "-").replace(/\//g, "_").replace(/=+$/, "");
}

export function concat(...parts: Uint8Array[]): Bytes {
  const joined = new Uint8Array(parts.reduce((total, part) => total + part.length, 0));
  let offset = 0;
  for (const part of parts) {
    joined.set(part, offset);
    offset += part.length;
  }
  return joined;
}

export async function hkdf(salt: Bytes, secret: Bytes, info: Bytes, length: number): Promise<Bytes> {
  const key = await crypto.subtle.importKey("raw", secret, "HKDF", false, ["deriveBits"]);
  const bits = await crypto.subtle.deriveBits({ name: "HKDF", hash: "SHA-256", salt, info }, key, length * 8);
  return new Uint8Array(bits);
}

/** Derives the content key and nonce that both sides of RFC 8291 compute. */
export async function deriveContentKeys(
  ecdhSecret: Bytes,
  authSecret: Bytes,
  subscriberPublic: Bytes,
  senderPublic: Bytes,
  salt: Bytes,
) {
  const keyInfo = concat(text.encode("WebPush: info\0"), subscriberPublic, senderPublic);
  const ikm = await hkdf(authSecret, ecdhSecret, keyInfo, 32);
  return {
    contentKey: await hkdf(salt, ikm, text.encode("Content-Encoding: aes128gcm\0"), 16),
    nonce: await hkdf(salt, ikm, text.encode("Content-Encoding: nonce\0"), 12),
  };
}

/** Encrypts one record for one subscriber, including the aes128gcm header. */
export async function encryptPayload(
  payload: Uint8Array,
  p256dh: string,
  auth: string,
  fixed?: { senderKeys: CryptoKeyPair; salt: Bytes },
): Promise<Bytes> {
  const subscriberPublic = fromBase64Url(p256dh);
  const senderKeys = fixed?.senderKeys ?? (await crypto.subtle.generateKey({ name: "ECDH", namedCurve: "P-256" }, true, ["deriveBits"]));
  const senderPublic = new Uint8Array(await crypto.subtle.exportKey("raw", senderKeys.publicKey));
  const subscriberKey = await crypto.subtle.importKey("raw", subscriberPublic, { name: "ECDH", namedCurve: "P-256" }, false, []);
  const shared = await crypto.subtle.deriveBits({ name: "ECDH", public: subscriberKey }, senderKeys.privateKey, 256);

  const salt = fixed?.salt ?? crypto.getRandomValues(new Uint8Array(16));
  const { contentKey, nonce } = await deriveContentKeys(new Uint8Array(shared), fromBase64Url(auth), subscriberPublic, senderPublic, salt);

  const key = await crypto.subtle.importKey("raw", contentKey, "AES-GCM", false, ["encrypt"]);
  const padded = concat(payload, Uint8Array.of(2));
  const cipher = new Uint8Array(await crypto.subtle.encrypt({ name: "AES-GCM", iv: nonce, tagLength: 128 }, key, padded));

  const recordSize = new Uint8Array(4);
  new DataView(recordSize.buffer).setUint32(0, RECORD_SIZE);
  return concat(salt, recordSize, Uint8Array.of(senderPublic.length), senderPublic, cipher);
}

/** A signed VAPID Authorization header for the push service that owns this endpoint. */
export async function vapidAuthorization(endpoint: string, keys: VapidKeys, nowSeconds: number): Promise<string> {
  const encode = (value: object) => toBase64Url(text.encode(JSON.stringify(value)));
  const claims = { aud: new URL(endpoint).origin, exp: nowSeconds + TOKEN_LIFETIME_S, sub: keys.subject };
  const unsigned = `${encode({ typ: "JWT", alg: "ES256" })}.${encode(claims)}`;
  const privateKey = await crypto.subtle.importKey(
    "jwk",
    JSON.parse(keys.privateJwk) as JsonWebKey,
    { name: "ECDSA", namedCurve: "P-256" },
    false,
    ["sign"],
  );
  const signature = await crypto.subtle.sign({ name: "ECDSA", hash: "SHA-256" }, privateKey, text.encode(unsigned));
  return `vapid t=${unsigned}.${toBase64Url(new Uint8Array(signature))}, k=${keys.publicKey}`;
}

/** Sends one push. Returns the push service's HTTP status. */
export async function sendPush(
  subscription: PushSubscriptionRecord,
  message: object,
  keys: VapidKeys,
  ttlSeconds: number,
): Promise<number> {
  const body = await encryptPayload(text.encode(JSON.stringify(message)), subscription.p256dh, subscription.auth);
  const response = await fetch(subscription.endpoint, {
    method: "POST",
    headers: {
      authorization: await vapidAuthorization(subscription.endpoint, keys, Math.floor(Date.now() / 1000)),
      "content-encoding": "aes128gcm",
      "content-type": "application/octet-stream",
      ttl: String(ttlSeconds),
      urgency: "high",
    },
    body,
  });
  return response.status;
}
