# Decisions (F-items)

| ID | Question | Status | Decision / next step |
| --- | --- | --- | --- |
| F1 | Tell a real bank call from a fake one | Decided | Decision checks direction + verified number; real-bank fixture must stay quiet (R7). Build the verified list. |
| F2 | Banking app open isn't visible | Decided | Detect bank-app traffic on the network (DNS); fails with encrypted DNS or Private Relay. Pitch as "bank-app traffic". |
| F3 | End the call or alert | Decided | Alert with three buttons; never auto hang-up (R2). |
| F4 | Outbound dial check | Parked | Later, if time. |
| F5 | Money back wording, credit card | Open | Say "files a cancel request"; confirm T-Mobile credit card exists before pitching it. |
| F6 | Nemotron's role | Decided | Every agent is a LangGraph node on Nemotron via Brev; Aftercare Planner shows its trace. |
| F7 | Which tracks | Open | Ask organizers if MLH prizes count toward the limit of 3. |
| F8 | Photon live call | Open | Ask Photon; fallback is our own conference bridge. |
| F9 | Pitch wording | Open | Proposed: "Your carrier's protection stops the moment you pick up." |
| F10 | Unsourced claims | Open | Only use `context/facts.md`. |
| F11 | Consent for listening | Open | Proposed: signals-only for everyone, transcript listening opt-in. |
| F12 | Data size, eval author | Open | Proposed: 500 to 1,500 sessions; eval set written by a different model or by hand. |
| F13 | LLM only raises risk | Adopted as R6 | Prove in Lean (Lane 2). |
| Jev | What Jev is and how we call it | Open | Behind `decide()`; rule fallback ready. |
