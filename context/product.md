# Product

## One line
Your carrier's protection stops the moment you pick up. Safe Signal covers the call itself, and cleans up after. (Final wording: F9.)

## Scope rule
- Calls T-Mobile already labels "Scam Likely" get **no agent**. We handle the gray zone: unlabeled inbound calls and calls the customer dials.
- In production this would live in T-Mobile's network and inside T-Life. For the hackathon: one web app (console, phone view, landing) plus real phone touchpoints through Photon.

## Before, during, after
| Phase | What happens | Agents |
| --- | --- | --- |
| Before | Number checked against scam data + anomaly detection before it rings | Caller Screen |
| During | Two triggers watched; Jev sets the level; customer alerted | Call Guardian, Signal Watcher, Decision, Alert |
| After | Planner decides steps; callback to the real number, recovery, evidence | Aftercare Planner, Callback, Recovery, Evidence |

## The two triggers
- **Trigger A, bank code mid-call:** a one-time code from a bank short code arrives, or bank-app traffic is seen, while the customer is on a call with an unknown or unverified number.
- **Trigger B, request against the customer's interest:** the caller asks for gift cards, the code, a "safe account", remote access, or claims something that contradicts T-Mobile's real policies (e.g. refunds by gift card).

## Alert levels (the ladder)
| Level | What the customer gets |
| --- | --- |
| `none` | Nothing |
| `nudge` | Silent on-screen card with the reason |
| `whisper` | Short ElevenLabs voice line only the customer hears, plus the card |
| `alert` | Photon notification with three buttons (call my bank on my card's number, ask my trusted contact, continue); SIM, port-out and forwarding changes held. **No hang-up.** |

Thresholds live in `services/agents/decision/config.py` and are tuned on the eval set.

## Non-goals (say no if asked)
Personalized protection based on profiling, auto hang-up, recording calls, building a standalone app, romance or investment scams that unfold over weeks, the outbound dial check (F4, parked).

## Glossary
- **Gray zone:** a call T-Mobile did not label.
- **Verified number:** a number on our verified-organization list (banks, T-Mobile care).
- **Hard negative:** a benign session that looks scammy (e.g. you call your bank and get a code).
- **F-items:** open decisions, see `context/decisions.md`.
