/** Jev's 12 red-flag questions, named in sandbox/jev.py, plus the live Call Guardian's card-details flag. */
export const RED_FLAGS = {
  asks_for_code: "Asks for a code",
  asks_for_pin_or_password: "Asks for a PIN or password",
  asks_for_card_details: "Asks for card details",
  asks_to_move_money: "Asks to move money",
  asks_for_gift_cards: "Asks for gift cards",
  asks_for_crypto_or_wire: "Asks for crypto or wire",
  asks_remote_access: "Asks for remote access",
  asks_secrecy: "Asks for secrecy",
  creates_urgency: "Creates urgency",
  threatens: "Makes threats",
  claims_authority: "Claims authority",
  emotional_family_emergency: "Family emergency story",
  verifies_safely: "Points to safe verification",
} as const;

export type RedFlag = keyof typeof RED_FLAGS;

export const RED_FLAG_ENTRIES = Object.entries(RED_FLAGS) as [RedFlag, string][];
