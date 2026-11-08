import { describe, expect, test } from "bun:test";
import { concat, deriveContentKeys, encryptPayload, fromBase64Url, toBase64Url, vapidAuthorization } from "../worker/webpush";
import { isPushEndpoint } from "../worker/hub-endpoints";
import { signNotice } from "../worker/realtime";

/** Plays the phone: decrypts what the server sent using only the subscriber's keys. */
async function decryptAsSubscriber(body: Uint8Array<ArrayBuffer>, privateKey: CryptoKey, subscriberPublic: Uint8Array<ArrayBuffer>, auth: Uint8Array<ArrayBuffer>) {
  const salt = body.slice(0, 16);
  const idLength = body[20];
  const senderPublic = body.slice(21, 21 + idLength);
  const cipher = body.slice(21 + idLength);
  const senderKey = await crypto.subtle.importKey("raw", senderPublic, { name: "ECDH", namedCurve: "P-256" }, false, []);
  const shared = new Uint8Array(await crypto.subtle.deriveBits({ name: "ECDH", public: senderKey }, privateKey, 256));
  const { contentKey, nonce } = await deriveContentKeys(shared, auth, subscriberPublic, senderPublic, salt);
  const key = await crypto.subtle.importKey("raw", contentKey, "AES-GCM", false, ["decrypt"]);
  return new Uint8Array(await crypto.subtle.decrypt({ name: "AES-GCM", iv: nonce, tagLength: 128 }, key, cipher));
}

describe("web push", () => {
  test("a subscriber can decrypt the payload", async () => {
    const keys = await crypto.subtle.generateKey({ name: "ECDH", namedCurve: "P-256" }, true, ["deriveBits"]);
    const publicKey = new Uint8Array(await crypto.subtle.exportKey("raw", keys.publicKey));
    const auth = crypto.getRandomValues(new Uint8Array(16));
    const message = new TextEncoder().encode(JSON.stringify({ title: "A code just arrived" }));

    const body = await encryptPayload(message, toBase64Url(publicKey), toBase64Url(auth));
    const plain = await decryptAsSubscriber(body, keys.privateKey, publicKey, auth);

    expect(plain[plain.length - 1]).toBe(2);
    expect(new TextDecoder().decode(plain.slice(0, -1))).toBe(JSON.stringify({ title: "A code just arrived" }));
    expect(body[20]).toBe(65);
  });

  test("the VAPID token is scoped to the push service and verifies", async () => {
    const keys = await crypto.subtle.generateKey({ name: "ECDSA", namedCurve: "P-256" }, true, ["sign", "verify"]);
    const publicKey = toBase64Url(new Uint8Array(await crypto.subtle.exportKey("raw", keys.publicKey)));
    const privateJwk = JSON.stringify(await crypto.subtle.exportKey("jwk", keys.privateKey));

    const header = await vapidAuthorization("https://fcm.googleapis.com/fcm/send/abc", { publicKey, privateJwk, subject: "https://example.test" }, 1000);
    const [, token, key] = /^vapid t=(.+), k=(.+)$/.exec(header) ?? [];
    const [head, claims, signature] = token.split(".");

    expect(key).toBe(publicKey);
    expect(JSON.parse(new TextDecoder().decode(fromBase64Url(claims)))).toEqual({
      aud: "https://fcm.googleapis.com",
      exp: 1000 + 12 * 60 * 60,
      sub: "https://example.test",
    });
    const valid = await crypto.subtle.verify(
      { name: "ECDSA", hash: "SHA-256" },
      keys.publicKey,
      fromBase64Url(signature),
      new TextEncoder().encode(`${head}.${claims}`),
    );
    expect(valid).toBe(true);
  });

  test("matches the published test vector in RFC 8291 appendix A", async () => {
    const asPublic = fromBase64Url("BP4z9KsN6nGRTbVYI_c7VJSPQTBtkgcy27mlmlMoZIIgDll6e3vCYLocInmYWAmS6TlzAC8wEqKK6PBru3jl7A8");
    const jwk = {
      kty: "EC",
      crv: "P-256",
      d: "yfWPiYE-n46HLnH0KqZOF1fJJU3MYrct3AELtAQ-oRw",
      x: toBase64Url(asPublic.slice(1, 33)),
      y: toBase64Url(asPublic.slice(33, 65)),
    };
    const params = { name: "ECDH", namedCurve: "P-256" };
    const senderKeys = {
      privateKey: await crypto.subtle.importKey("jwk", jwk, params, true, ["deriveBits"]),
      publicKey: await crypto.subtle.importKey("raw", asPublic, params, true, []),
    };
    const body = await encryptPayload(
      new TextEncoder().encode("When I grow up, I want to be a watermelon"),
      "BCVxsr7N_eNgVRqvHtD0zTZsEc6-VV-JvLexhqUzORcxaOzi6-AYWXvTBHm4bjyPjs7Vd8pZGH6SRpkNtoIAiw4",
      "BTBZMqHH6r4Tts7J_aSIgg",
      { senderKeys, salt: fromBase64Url("DGv6ra1nlYgDCS1FRnbzlw") },
    );
    expect(toBase64Url(body)).toBe(
      "DGv6ra1nlYgDCS1FRnbzlwAAEABBBP4z9KsN6nGRTbVYI_c7VJSPQTBtkgcy27mlmlMoZIIgDll6e3vCYLocInmYWAmS6TlzAC8wEqKK6PBru3jl7A_yl95bQpu6cVPTpK4Mqgkf1CXztLVBSt2Ks3oZwbuwXPXLWyouBWLVWGNWQexSgSxsj_Qulcy4a-fN",
    );
  });

  test("joins byte arrays in order", () => {
    expect([...concat(Uint8Array.of(1), Uint8Array.of(2, 3))]).toEqual([1, 2, 3]);
  });

  test("only real push services are accepted as endpoints", () => {
    expect(isPushEndpoint("https://fcm.googleapis.com/fcm/send/abc")).toBe(true);
    expect(isPushEndpoint("https://evil.example/fcm.googleapis.com/")).toBe(false);
    expect(isPushEndpoint("http://fcm.googleapis.com/fcm/send/abc")).toBe(false);
    expect(isPushEndpoint("https://fcm.googleapis.com.evil.example/x")).toBe(false);
  });
});

describe("realtime signing", () => {
  test("a signed notice verifies, and a changed one does not", async () => {
    const params = { name: "ECDSA", namedCurve: "P-256" };
    const keys = await crypto.subtle.generateKey(params, true, ["sign", "verify"]);
    const jwk = JSON.stringify(await crypto.subtle.exportKey("jwk", keys.privateKey));
    const wire = { id: "a", at: 1, level: "quiet" as const, notice: { channel: "t-life" as const, timing: "during-call" as const, title: "T", body: "B" } };

    const { n, s } = await signNotice(wire, jwk);
    const verify = (text: string) =>
      crypto.subtle.verify({ name: "ECDSA", hash: "SHA-256" }, keys.publicKey, fromBase64Url(s), new TextEncoder().encode(text));

    expect(await verify(n)).toBe(true);
    expect(await verify(n.replace('"T"', '"Send money now"'))).toBe(false);
  });
});
