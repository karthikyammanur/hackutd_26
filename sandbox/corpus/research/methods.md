# Scam methods

Awareness-level reference for the method ids in `sandbox/worker/src/taxonomy.py`. It describes how to recognize these scams, not how to run one. Links and how each was retrieved are in [sources.md](sources.md).

**Persuasion shorthand** (general categories, drawn from the social-engineering literature): authority, urgency, fear, scarcity, trust or liking, reciprocity, social proof, secrecy, distraction.

## Impersonation
| Method | Typical stages | Persuasion | Channels | Detection signals | Source |
| --- | --- | --- | --- | --- | --- |
| `bank_fraud_department` | Alert about fraud, offer to help, code or "safe account" request | Authority, fear, urgency, secrecy | Call, text | Asks for a code or to move money; code text or bank app use during the call | [FTC](https://consumer.ftc.gov/consumer-alerts/2024/03/never-move-your-money-protect-it-thats-scam) |
| `text_then_call_fraud_alert` | Fake alert text, victim replies, "fraud team" calls, safe-account request | Authority, fear, urgency | Text then call | Fraud-alert text shortly before an unknown call; same story across channels | [FTC](https://www.ftc.gov/news-events/data-visualizations/data-spotlight/2025/04/top-text-scams-2024) |
| `phantom_hacker` | Fake tech support gets remote access; fake bank warns of hackers; fake government agent confirms | Authority, fear, secrecy | Call, pop-up, letter | Remote-access request, then several "agencies" in sequence; secrecy about moving savings | [FBI](https://www.fbi.gov/news/podcasts/inside-the-fbi-podcast-the-phantom-hacker-scam) |
| `government_impersonation` | Claims a legal or benefits problem, threat, payment or data demand | Authority, fear, urgency | Call, text, robocall | Arrest or suspension threats; payment by gift card, wire or crypto | [FTC](https://consumer.ftc.gov/articles/phone-scams) |
| `carrier_impersonation` | Billing or refund pretext, asks for PIN or code | Authority, reciprocity | Call, text | Carrier claim plus PIN or one-time code request; SIM or port-out attempt during the call | [T-Mobile](https://www.t-mobile.com/dialed-in/tips-tricks/avoid-phone-scams) |
| `brand_order_impersonation` | Suspicious order claim, press a key or call back, card or remote-access request | Fear, urgency | Robocall, text | Named retailer with an unrecognized order; "press 1" prompt | [FTC](https://consumer.ftc.gov/features/robocall-scam-examples) |
| `tech_support` | Claimed device problem, remote access, payment | Authority, fear | Call, pop-up | Remote-access app request; unsolicited support contact | [FTC](https://consumer.ftc.gov/articles/how-spot-avoid-and-report-tech-support-scams) |
| `utility_shutoff` | Same-day shutoff threat, immediate payment | Fear, urgency | Call, robocall | Same-day disconnection; barcode, gift card or app payment | [FTC](https://consumer.ftc.gov/articles/scammers-pretend-be-your-utility-company) |
| `family_emergency_voice_clone` | Relative in crisis, secrecy, money for bail or a hospital | Fear, trust, urgency, secrecy | Call | Claimed relative plus untraceable payment; failed safe word | [FTC](https://consumer.ftc.gov/consumer-alerts/2023/03/scammers-use-ai-enhance-their-family-emergency-schemes), [FBI](https://www.ic3.gov/PSA/2024/PSA241203) |
| `family_emergency_text` | "New number, broken phone", move to a chat app, money request | Trust, urgency | Text, chat app | Relative claim from an unknown number | [IMC 2025](https://github.com/reportsmishing/Smishing-Dataset-IMC25) |
| `executive_or_coworker` | Message from "boss", urgent favor, gift cards | Authority, urgency | Text, call, email | Boss claim from an unfamiliar number; gift card request | [FTC](https://consumer.ftc.gov/consumer-alerts/2026/01/no-thats-not-your-boss-asking-you-buy-gift-cards) |
| `healthcare_benefits` | Medicare or benefit pretext, asks for ID number or payment | Authority, reciprocity | Call, text | Unsolicited request for a Medicare number | [FTC](https://consumer.ftc.gov/consumer-alerts/2025/09/medicare-open-enrollment-season-learn-how-protect-yourself-scams) |
| `debt_collection` | Unrecognized debt, threats, immediate payment | Fear, authority | Call | Arrest threats; refusal to validate the debt in writing | [FTC](https://consumer.ftc.gov/articles/fake-abusive-debt-collectors) |

## Payment lures
| Method | Typical stages | Persuasion | Channels | Detection signals | Source |
| --- | --- | --- | --- | --- | --- |
| `delivery_fee` | Delivery problem, lookalike site, small fee | Urgency, distraction | Text | Courier claim, small fee, new domain | [FTC](https://www.ftc.gov/news-events/data-visualizations/data-spotlight/2025/04/top-text-scams-2024) |
| `toll_unpaid` | Unpaid balance, payment link | Fear, urgency | Text | Toll agency claim, unofficial domain | [FTC](https://www.ftc.gov/news-events/data-visualizations/data-spotlight/2025/04/top-text-scams-2024) |
| `refund_overpayment` | Refund promised, "overpaid", asks for money back | Reciprocity, urgency | Call, email | Refund plus gift cards or remote access | [FTC](https://consumer.ftc.gov/articles/how-spot-avoid-and-report-tech-support-scams) |
| `prize_lottery` | Prize claim, fee or taxes due | Scarcity, reciprocity | Call, text | Prize requiring payment first | [FTC](https://consumer.ftc.gov/articles/phone-scams) |
| `subscription_callback` | Fake renewal notice, call this number, remote access | Fear, urgency | Email, text, then call | Unknown charge with a number to call within a deadline | [FTC](https://consumer.ftc.gov/consumer-alerts/2018/02/phishers-send-fake-invoices) |
| `student_loan_relief` | Forgiveness offer, upfront fee or login | Authority, scarcity | Robocall, text | Forgiveness "center"; fee; links outside StudentAid.gov | [FTC](https://consumer.ftc.gov/features/robocall-scam-examples) |
| `credit_debt_relief` | Lower-rate offer, upfront fee | Scarcity, urgency | Robocall | "Rate expires" pressure; fee before service | [FTC](https://consumer.ftc.gov/articles/phone-scams) |
| `advance_fee_loan` | Guaranteed loan, upfront payment | Reciprocity | Call | Guarantee plus upfront fee | [FTC](https://consumer.ftc.gov/articles/phone-scams) |
| `auto_warranty` | Expiry claim, contract sale | Urgency, fear | Robocall | "Final notice" about a car warranty | [FTC](https://consumer.ftc.gov/consumer-alerts/2023/03/what-know-about-auto-service-contracts-extended-warranty-scams) |
| `deceptive_telemarketing` | Free trial, discount or trip, fees | Reciprocity, scarcity | Robocall | Illegal prerecorded sales offer | [FTC](https://consumer.ftc.gov/articles/phone-scams) |
| `one_ring_wangiri` | Single ring, victim calls back, charges | Curiosity | Call | Very short missed call from a lookalike international code | [FCC](https://www.fcc.gov/scam-glossary) |

## Credential theft
| Method | Typical stages | Persuasion | Channels | Detection signals | Source |
| --- | --- | --- | --- | --- | --- |
| `account_verification_phish` | Account warning, login link | Fear, urgency | Text, email | Verify-your-account link; new domain | [FTC](https://consumer.ftc.gov/all-scams/phishing-scams) |
| `generic_smishing` | Unsolicited text, link or reply | Varies | Text | Link from an unknown sender | [FTC](https://consumer.ftc.gov/articles/how-recognize-and-report-spam-text-messages) |
| `qr_code_phish` | QR code on a package, notice or message, fake site or payment | Curiosity, authority | Physical item, text | Unexpected QR code leading to a login or payment page | [FBI](https://www.fbi.gov/contact-us/field-offices/elpaso/news/fbi-tech-tuesday-building-a-digital-defense-against-qr-code-scams) |
| `sim_swap_port_out` | Criminal poses as the customer to the carrier; number moved; codes intercepted | Deception of carrier staff | Carrier channels | SIM or port-out attempt; sudden loss of service | [FTC](https://consumer.ftc.gov/consumer-alerts/2019/10/sim-swap-scams-how-protect-yourself), [FCC](https://www.fcc.gov/cell-phone-fraud) |
| `otp_interception` | Support pretext, a real login triggers a code, victim reads it out | Authority, urgency | Call, chat | Code text arrives during a call; caller asks for it | [FBI](https://www.fbi.gov/investigate/cyber/alerts/2025/account-takeover-fraud-via-impersonation-of-financial-institution-support), [FTC](https://consumer.ftc.gov/consumer-alerts/2024/03/whats-verification-code-why-would-someone-ask-me-it) |
| `survey_voice_harvest` | Harmless survey collects details and voice, used for later fraud | Liking | Call | Long personal or financial survey from an unknown caller | [Greenwich](https://www.royalgreenwich.gov.uk/news/2026/phone-scam-uses-ai-clone-victims-voices) |

## Relationship or opportunity
| Method | Typical stages | Persuasion | Channels | Detection signals | Source |
| --- | --- | --- | --- | --- | --- |
| `job_task_scam` | Unsolicited offer, easy tasks, pay to continue | Reciprocity, scarcity | Text, chat app | Job with no details; asked to send money to withdraw earnings | [FTC](https://www.ftc.gov/news-events/data-visualizations/data-spotlight/2025/04/top-text-scams-2024), [FTC jobs](https://consumer.ftc.gov/articles/job-scams) |
| `investment_crypto` | Rapport or tip, fake platform, growing deposits | Social proof, scarcity | Call, text, social | Guaranteed returns; crypto deposit request | [FTC](https://consumer.ftc.gov/articles/phone-scams) |
| `wrong_number_romance` | Mistaken text, friendship, investment pitch | Liking, trust | Text, chat app | Greeting from a stranger that continues after correction | [FTC](https://www.ftc.gov/news-events/data-visualizations/data-spotlight/2025/04/top-text-scams-2024) |
| `romance` | Online relationship, invented emergency, payment | Liking, trust | Social, text | Partner never meets; wire, gift card or crypto requests | [FTC](https://consumer.ftc.gov/articles/what-know-about-romance-scams) |
| `charity_disaster` | Disaster appeal, immediate donation | Reciprocity, urgency | Call, text | Pressure to give right away; untraceable payment | [FTC](https://consumer.ftc.gov/articles/phone-scams) |
| `marketplace_rental` | Fake listing or buyer, deposit or overpayment | Scarcity, trust | Text, marketplace | Overpayment refund; deposit before viewing | [FTC checks](https://consumer.ftc.gov/articles/how-spot-avoid-and-report-fake-check-scams), [FTC rentals](https://consumer.ftc.gov/articles/rental-listing-scams) |

## Mapping to the T-Mobile challenge
| Judging focus | What the sandbox can measure |
| --- | --- |
| Detection accuracy | Catch rate, false alarms and hard-negative false alarms, by method and model. Exact-label data only for headline numbers. |
| Honest confidence | How well `P(dangerous)` matches real outcomes (calibration); how often calls land in `uncertain`; `no_verdict` counted rather than hidden. |
| Clear next steps and impact | Share flagged before `money_moment_t`; per-frame latency. |
| Usability | Share of legitimate calls interrupted, especially real bank and carrier calls. |
| Security and privacy | Results hold only scores, flags, ids and markers. Public text is redacted. The label-leaking `caller` field is removed. |
| Creativity | Coverage across channels and of multi-step methods such as `text_then_call_fraud_alert` and `phantom_hacker`. |

The challenge mentions a provided synthetic message set, scam taxonomy and baseline classifier. I couldn't find those files in the test folder, so nothing here is compared against them.

## Known measurement risks
- **Source confound in `sms_public`:** scams are mostly from IMC and legitimate messages from UCI and Mendeley, so a model could separate them by writing style or era. Don't quote these as headline accuracy.
- **Robocalls are one-sided recordings** and are all scam-side, so they measure catch rate only, not false alarms.
