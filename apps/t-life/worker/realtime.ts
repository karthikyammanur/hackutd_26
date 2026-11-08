import type { WireNotice } from "../src/lib/notices";
import { toBase64Url } from "./webpush";

/**
 * Fast fan-out to every open app, over Server-Sent Events through ntfy.sh.
 * The relay is public and anyone could post to the topic, so each notice is signed here and the
 * app verifies it. The text is the fixed, synthetic demo copy, which is already public in the app.
 */

export interface RealtimeEnv {
  REALTIME_TOPIC: string;
  REALTIME_PUBLIC_KEY: string;
  REALTIME_PRIVATE_JWK: string;
}

const RELAY = "https://ntfy.sh";

export interface RelayMessage {
  url: string;
  body: string;
}

export interface SignedNotice {
  /** The notice as JSON. Signed as these exact bytes. */
  n: string;
  s: string;
}

export async function signNotice(wire: WireNotice, privateJwk: string): Promise<SignedNotice> {
  const key = await crypto.subtle.importKey("jwk", JSON.parse(privateJwk) as JsonWebKey, { name: "ECDSA", namedCurve: "P-256" }, false, ["sign"]);
  const n = JSON.stringify(wire);
  const signature = await crypto.subtle.sign({ name: "ECDSA", hash: "SHA-256" }, key, new TextEncoder().encode(n));
  return { n, s: toBase64Url(new Uint8Array(signature)) };
}

/** What the sender's browser should post. The relay rate-limits Cloudflare's shared addresses. */
export async function relayMessage(env: RealtimeEnv, wire: WireNotice): Promise<RelayMessage> {
  return { url: `${RELAY}/${env.REALTIME_TOPIC}`, body: JSON.stringify(await signNotice(wire, env.REALTIME_PRIVATE_JWK)) };
}
