# Sources

## Datasets
| Dataset | Used as | License | Citation and link |
| --- | --- | --- | --- |
| Robocall Audio Dataset (NC State), transcripts supplied in `message.txt` | `robocall_public.jsonl` | Data public domain; documentation CC BY-ND | Prasad and Reaves, "Robocall Audio from the FTC's Project Point of No Entry", NCSU TR-2023-1, 2023. https://github.com/wspr-ncsu/robocall-audio-dataset |
| Fishing for Smishing (IMC 2025) | `sms_public.jsonl`, English rows | CC BY 4.0 | Agarwal, Papasavva, Suarez-Tangil and Vasek, IMC 2025, https://doi.org/10.1145/3730567.3764431. https://github.com/reportsmishing/Smishing-Dataset-IMC25 |
| SMS Phishing Dataset | `sms_public.jsonl` | CC BY 4.0 | Mishra and Soni, Mendeley Data, https://doi.org/10.17632/f45bkkt8pr.1 |
| SMS Spam Collection | `sms_public.jsonl` | CC BY 4.0 | Almeida and Hidalgo, UCI ML Repository, 2011, https://doi.org/10.24432/C5CC84 |

Changes made to all of the above: converted to Case format, digit runs of 5 or more replaced with `[number]`, anonymization tokens rewritten as bracketed words, duplicates removed. Scam method labels on the robocall, Mendeley and UCI data are inferred by the keyword rules in `build_external.py`.

### Label limits
- **Robocalls:** the dataset says most recordings are *suspected* illegal calls and that a majority were used to defraud. Not every record is a confirmed scam, so all are `weak`.
- **Rule check:** 81 records carried a usable topic tag in their id; the rules agreed with 77. That's a small, non-random check.
- **UCI and Mendeley "spam":** spam isn't always a scam. Spam with no scam-method keyword was excluded. Older UK and Indian messages remain and are not representative of current US traffic.
- **Mendeley:** text came from images run through OCR, so expect recognition errors.
- **IMC:** drawn from public user reports. Only English rows are used, and the labels `others`, `spam` and blank are excluded.

### Not retrieved
- **Smishing Dataset I (Timko and Rahman, smishtank.com):** I found the paper (arXiv 2402.18430) but no direct download.
- **Public, labeled scam call transcripts with multiple turns:** none found. The robocall set has single-sided, recorded messages only.

## Method references
Fetched directly and read:
- FTC: [top text scams of 2024](https://www.ftc.gov/news-events/data-visualizations/data-spotlight/2025/04/top-text-scams-2024), [phone scams](https://consumer.ftc.gov/articles/phone-scams), [AI family-emergency schemes](https://consumer.ftc.gov/consumer-alerts/2023/03/scammers-use-ai-enhance-their-family-emergency-schemes), [fake checks](https://consumer.ftc.gov/articles/how-spot-avoid-and-report-fake-check-scams), [rental listings](https://consumer.ftc.gov/articles/rental-listing-scams), [romance](https://consumer.ftc.gov/articles/what-know-about-romance-scams), [job scams](https://consumer.ftc.gov/articles/job-scams), [SIM swaps](https://consumer.ftc.gov/consumer-alerts/2019/10/sim-swap-scams-how-protect-yourself), [moving money to "protect it"](https://consumer.ftc.gov/consumer-alerts/2024/03/never-move-your-money-protect-it-thats-scam)
- FBI/IC3: [generative AI in financial fraud, PSA I-120324](https://www.ic3.gov/PSA/2024/PSA241203)
- Dataset pages for UCI, Mendeley, IMC 2025 and the NC State robocall set

Read as search-result excerpts, not fetched in full:
- FTC: [utility impostors](https://consumer.ftc.gov/articles/scammers-pretend-be-your-utility-company), [fake debt collectors](https://consumer.ftc.gov/articles/fake-abusive-debt-collectors), [boss gift-card scams](https://consumer.ftc.gov/consumer-alerts/2026/01/no-thats-not-your-boss-asking-you-buy-gift-cards), [Medicare](https://consumer.ftc.gov/consumer-alerts/2025/09/medicare-open-enrollment-season-learn-how-protect-yourself-scams), [fake invoices and callbacks](https://consumer.ftc.gov/consumer-alerts/2018/02/phishers-send-fake-invoices), [tech support](https://consumer.ftc.gov/articles/how-spot-avoid-and-report-tech-support-scams), [verification codes](https://consumer.ftc.gov/consumer-alerts/2024/03/whats-verification-code-why-would-someone-ask-me-it), [robocall examples](https://consumer.ftc.gov/features/robocall-scam-examples), [auto warranties](https://consumer.ftc.gov/consumer-alerts/2023/03/what-know-about-auto-service-contracts-extended-warranty-scams), [spam texts](https://consumer.ftc.gov/articles/how-recognize-and-report-spam-text-messages), [phishing](https://consumer.ftc.gov/all-scams/phishing-scams), [2025 imposter losses](https://ftc.gov/news-events/news/press-releases/2026/06/ftc-data-show-people-reported-losing-3-point-5-billion-imposter-scams-2025)
- FBI: [Phantom Hacker](https://www.fbi.gov/news/podcasts/inside-the-fbi-podcast-the-phantom-hacker-scam), [account takeover via fake bank support](https://www.fbi.gov/investigate/cyber/alerts/2025/account-takeover-fraud-via-impersonation-of-financial-institution-support), [QR codes](https://www.fbi.gov/contact-us/field-offices/elpaso/news/fbi-tech-tuesday-building-a-digital-defense-against-qr-code-scams)
- FCC: [scam glossary, one-ring calls](https://www.fcc.gov/scam-glossary) and [cell phone fraud](https://www.fcc.gov/cell-phone-fraud). Direct fetches of FCC pages returned 403.
- [T-Mobile scam guide](https://www.t-mobile.com/dialed-in/tips-tricks/avoid-phone-scams), [Royal Greenwich council on survey voice cloning](https://www.royalgreenwich.gov.uk/news/2026/phone-scam-uses-ai-clone-victims-voices)
- Persuasion: [Ferreira, Coventry and Lenzini 2015](https://orbilu.uni.lu/handle/10993/20301), [scam-baiting call stages, arXiv 2307.01965](https://arxiv.org/pdf/2307.01965). Full texts not read, so category names in `methods.md` are general ones.

Weaker support:
- `family_emergency_text` is backed by the IMC dataset's `hey mum/dad` label, not a US agency page.
- `survey_voice_harvest` rests on a UK local-government warning.
- `carrier_impersonation` is sourced to T-Mobile's general scam guide.
