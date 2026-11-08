// TypeSafe Jev client: one request per microframe, three danger tiers plus narrow red-flag questions.
// Same questions as sandbox/jev.py (originally test/jev-lab/scam.ts).

const API = "https://api.typesafe.ai/v1/systemone";
export type Tier = "safe" | "uncertain" | "dangerous";
export const TIER_RANK: Record<Tier, number> = { safe: 0, uncertain: 1, dangerous: 2 };

export const FLAGS: Record<string, [string, string, string]> = {
  asks_for_code: [
    "Is the CALLER asking the customer to read out, type, or share a one-time code, verification number, or digits that were just sent to their phone?",
    "Any request to read back or share a code or digits that arrived by text, even if worded vaguely",
    "No such request, or the caller says they will never ask for a code",
  ],
  asks_for_pin_or_password: [
    "Is the CALLER asking for an account PIN, passcode, password, or security answer?",
    "Asks for a PIN, passcode, password, the last digits of an account number, or a secret answer",
    "No such request",
  ],
  asks_to_move_money: [
    "Is the CALLER asking the customer to move, transfer, wire, or withdraw money to a 'safe', 'secure', 'holding', or new account, or to hand cash to a courier?",
    "Any instruction to move money somewhere for protection or to a new recipient",
    "No request to move money",
  ],
  asks_for_gift_cards: [
    "Is the CALLER asking for payment with gift cards, store cards, or prepaid vouchers, or to read numbers off the back of a card?",
    "Gift cards, store vouchers, prepaid cards, or reading card numbers aloud",
    "No gift card or voucher payment",
  ],
  asks_for_crypto_or_wire: [
    "Is the CALLER asking for payment by cryptocurrency, a crypto ATM, a wire transfer, or a payment app?",
    "Crypto, bitcoin ATM, wire, Zelle, Cash App, or similar",
    "No such payment request",
  ],
  asks_remote_access: [
    "Is the CALLER asking the customer to install an app or give remote access to their phone or computer?",
    "Install a remote-support app, share their screen, or let the caller control the device",
    "No such request",
  ],
  asks_secrecy: [
    "Is the CALLER asking the customer to keep this secret, not tell family or the bank, or stay on the line and not hang up?",
    "Any instruction to hide it from others or not to hang up",
    "No secrecy request",
  ],
  creates_urgency: [
    "Is the CALLER pressuring the customer to act immediately?",
    "Deadlines in minutes or hours, 'right now', 'before it's too late'",
    "No time pressure",
  ],
  threatens: [
    "Is the CALLER threatening arrest, legal action, fines, frozen accounts, or cut-off service?",
    "Any threat of a bad consequence if the customer doesn't comply",
    "No threats",
  ],
  claims_authority: [
    "Does the CALLER claim to be from a bank, the phone carrier, a government agency, a tech company, or the police?",
    "Claims to represent such an organization",
    "No such claim",
  ],
  emotional_family_emergency: [
    "Does the CALLER claim to be a family member in an emergency (accident, arrest, hospital, stranded) who needs money?",
    "A relative in trouble asking for money",
    "No family emergency story",
  ],
  verifies_safely: [
    "Does the CALLER tell the customer to hang up and call the official number on their card or the company's website, or say they will never ask for codes or PINs?",
    "Points the customer to an independent, official way to verify",
    "Does not",
  ],
};

export function buildQuestions(): Record<string, unknown> {
  const questions: Record<string, unknown> = {};
  for (const [name, [q, yes, no]] of Object.entries(FLAGS)) {
    questions[name] = { type: "noul", instructions: q, criteria: { true: yes, false: no } };
  }
  questions.danger_tier = {
    type: "choice",
    instructions: "Based only on the call so far, which tier best describes the scam danger to the customer?",
    criteria: {
      safe: "A normal, legitimate conversation. Nothing is being asked that a real business, friend or relative would not ask",
      uncertain:
        "Something is slightly off or could go either way, but there is no clear attempt yet to get money, codes, credentials or device access",
      dangerous:
        "The caller is manipulating the customer toward losing money, codes, credentials or device access, including impersonating an organization or a relative",
    },
  };
  return questions;
}

export interface JevResult {
  tier: Tier;
  probabilities: Record<string, number>;
  flags: Record<string, number>;
  inputTokens: number;
  outputTokens: number;
  latencyMs: number;
}

export function parseAnswer(body: any, latencyMs: number): JevResult {
  const tier = body?.answers?.danger_tier;
  if (!tier || !(tier.choice in TIER_RANK) || typeof tier.probabilities !== "object") {
    throw new Error("bad Jev response: danger_tier");
  }
  const flags: Record<string, number> = {};
  for (const name of Object.keys(FLAGS)) {
    const p = body.answers[name]?.noul;
    if (typeof p !== "number") throw new Error(`bad Jev response: ${name}`);
    flags[name] = p;
  }
  return {
    tier: tier.choice,
    probabilities: tier.probabilities,
    flags,
    inputTokens: Number(body.usage?.input_tokens ?? 0),
    outputTokens: Number(body.usage?.output_tokens ?? 0),
    latencyMs,
  };
}

const sleep = (ms: number) => new Promise((resolve) => setTimeout(resolve, ms));

export async function classify(apiKey: string, model: string, state: string, attempts = 3): Promise<JevResult> {
  let last = "no attempts";
  for (let attempt = 0; attempt < attempts; attempt++) {
    const started = Date.now();
    try {
      const response = await fetch(API, {
        method: "POST",
        headers: { authorization: `Bearer ${apiKey}`, "content-type": "application/json" },
        body: JSON.stringify({ model, state, questions: buildQuestions() }),
        signal: AbortSignal.timeout(15000),
      });
      if (response.ok) return parseAnswer(await response.json(), Date.now() - started);
      last = `HTTP ${response.status}`;
      if (response.status !== 429 && response.status < 500) throw new Error(last);
    } catch (error) {
      const message = error instanceof Error ? error.message : String(error);
      if (message.startsWith("bad Jev") || /^HTTP 4/.test(message)) throw error;
      last = message;
    }
    await sleep(1000 * 2 ** attempt);
  }
  throw new Error(`Jev failed: ${last}`);
}
