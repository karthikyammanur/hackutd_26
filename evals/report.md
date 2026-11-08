# Safe Signal eval report

**Lane 2 baseline: the 80% catch-rate gate failed.** These numbers were measured without the real Call Guardian, so treat them as a floor. Don't quote them on the Devpost without saying so (R18).

| Metric, on the frozen eval set | Signals only | Signals + keyword stand-in | Target |
| --- | --- | --- | --- |
| Catch rate at `alert` | 14.3% (10/70) | **47.1% (33/70)** | at least 80% |
| False `alert`, all benign | 0.0% (0/55) | 1.8% (1/55) | at most 5% |
| False `alert`, hard negatives | 0.0% (0/40) | 2.5% (1/40) | report honestly |
| R7: sessions the customer dialed to a verified number that stayed at or below `nudge` | 14/14 | 14/14 | all |
| Time to detect, median (only scams that reached `whisper`) | +1.5 s (n=28) | +0.0 s (n=49) | at or before the ask |
| Calibration (ECE) | 0.242 | 0.095 | report it |
| Decision latency, p95 | 0.016 ms | 0.019 ms | under 100 ms |

## What was measured
The Lane 2 pipeline only: Caller Screen, Signal Watcher and `decide()`, replayed by `evals/replay.py`.

- **Signals only** uses no transcript at all: only the call metadata and Trigger A.
- **Signals + keyword stand-in** adds `evals/stand_in_guardian.py`, a small set of regexes in the place where Call Guardian goes. It is not Nemotron.

The real pipeline needs Lane 1's graph (L1-3), which doesn't exist yet. Task L2-5 stays open until this is re-run through it.

## Reading the result
- Where the 70 scams ended up with the keyword stand-in: 33 `alert`, 16 `whisper`, 16 `nudge`, 5 `none`.
- The one false alert is `ev_ithelp_001`, a real IT help desk remoting into a laptop.
- Signals alone do catch SIM-swap attacks (8/9), since those show up as an account change. Most other scams need the transcript.
- Keyword rules scored 330/333 at `alert` on the template-generated training data and 33/70 here. Templates share phrasing with the rules, and natural speech doesn't. Train numbers say nothing about real performance.

## How far to trust these numbers
- **Written first.** The 125 sessions were written one at a time, not by the forge generator, before any rule or threshold existed, with 32% hard negatives.
- **Tuned elsewhere.** Thresholds and regexes were only adjusted using `data/train`, the fixtures and the red-team attacks. `evals/tune.py` refuses to read `data/eval`.
- **Run once.** The rules were frozen before this run and nothing changed after it.
- **Weakness: same author.** The eval set and the rules share an author, so the set is independent of the Nemotron generator but not of the rules. The author knew the general policy, so a teammate-written eval set would be a stronger test.
- **Small set.** Per-type rows have 3 to 15 sessions. Read them as directions, not rates.
- **Synthetic.** Every session is fictional (R10), so this says nothing about real call audio or speech-to-text errors.
- **Any rule change now spends this set.** If the rules or thresholds change after reading this report, write a new eval set before quoting new numbers.

The full `run_eval.py` output for both runs follows. Its latency lines round to 0 ms because each decision takes microseconds.

# Run 1: signals only

Sessions: 125 (70 scam, 55 benign, 40 hard negatives). Missing predictions: 0.

### Catch rate and false interventions

| Level reached | Catch rate (scam) | False rate (benign) | False rate (hard negatives) |
| --- | --- | --- | --- |
| nudge | 60.0% (42/70) | 18.2% (10/55) | 25.0% (10/40) |
| whisper | 40.0% (28/70) | 7.3% (4/55) | 10.0% (4/40) |
| alert | 14.3% (10/70) | 0.0% (0/55) | 0.0% (0/40) |

### Catch rate at alert, by scam type

| Type | Catch rate |
| --- | --- |
| bank_safe_account | 0.0% (0/15) |
| carrier_sim_swap | 88.9% (8/9) |
| fake_support_outbound | 0.0% (0/9) |
| family_emergency_scam | 0.0% (0/7) |
| gov_impersonation | 0.0% (0/9) |
| refund_overpayment | 0.0% (0/4) |
| signal_only_quiet | 66.7% (2/3) |
| tech_support_remote | 0.0% (0/9) |
| utility_shutoff | 0.0% (0/5) |

### False alerts on benign sessions, by type

| Type | False alert rate |
| --- | --- |
| benign_bank_callback | 0.0% (0/8) |
| benign_bank_inbound | 0.0% (0/4) |
| benign_carrier_care | 0.0% (0/6) |
| benign_doctor_office | 0.0% (0/6) |
| benign_family_emergency | 0.0% (0/5) |
| benign_it_helpdesk | 0.0% (0/3) |
| benign_otp_coincidence | 0.0% (0/3) |
| benign_personal | 0.0% (0/7) |
| benign_recruiter | 0.0% (0/5) |
| benign_service | 0.0% (0/8) |

### Time to detect (first whisper or higher, seconds after the scam ask)

Median +1.5 s, p90 +15.0 s, n=28. Negative means caught before the ask.

### Calibration (ECE 0.242, lower is better)

| Score bin | Sessions | Mean score | Share actually scam |
| --- | --- | --- | --- |
| 0.0-0.2 | 54 | 0.08 | 0.20 |
| 0.2-0.4 | 27 | 0.25 | 0.93 |
| 0.4-0.6 | 15 | 0.48 | 0.60 |
| 0.6-0.8 | 19 | 0.68 | 0.79 |
| 0.8-1.0 | 10 | 0.86 | 1.00 |

### Latency

p50 0 ms, p95 0 ms, n=970.

# Run 2: signals + keyword stand-in

Sessions: 125 (70 scam, 55 benign, 40 hard negatives). Missing predictions: 0.

### Catch rate and false interventions

| Level reached | Catch rate (scam) | False rate (benign) | False rate (hard negatives) |
| --- | --- | --- | --- |
| nudge | 92.9% (65/70) | 29.1% (16/55) | 40.0% (16/40) |
| whisper | 70.0% (49/70) | 9.1% (5/55) | 12.5% (5/40) |
| alert | 47.1% (33/70) | 1.8% (1/55) | 2.5% (1/40) |

### Catch rate at alert, by scam type

| Type | Catch rate |
| --- | --- |
| bank_safe_account | 33.3% (5/15) |
| carrier_sim_swap | 100.0% (9/9) |
| fake_support_outbound | 44.4% (4/9) |
| family_emergency_scam | 28.6% (2/7) |
| gov_impersonation | 44.4% (4/9) |
| refund_overpayment | 25.0% (1/4) |
| signal_only_quiet | 66.7% (2/3) |
| tech_support_remote | 55.6% (5/9) |
| utility_shutoff | 20.0% (1/5) |

### False alerts on benign sessions, by type

| Type | False alert rate |
| --- | --- |
| benign_bank_callback | 0.0% (0/8) |
| benign_bank_inbound | 0.0% (0/4) |
| benign_carrier_care | 0.0% (0/6) |
| benign_doctor_office | 0.0% (0/6) |
| benign_family_emergency | 0.0% (0/5) |
| benign_it_helpdesk | 33.3% (1/3) |
| benign_otp_coincidence | 0.0% (0/3) |
| benign_personal | 0.0% (0/7) |
| benign_recruiter | 0.0% (0/5) |
| benign_service | 0.0% (0/8) |

### Time to detect (first whisper or higher, seconds after the scam ask)

Median +0.0 s, p90 +15.0 s, n=49. Negative means caught before the ask.

### Calibration (ECE 0.095, lower is better)

| Score bin | Sessions | Mean score | Share actually scam |
| --- | --- | --- | --- |
| 0.0-0.2 | 40 | 0.07 | 0.07 |
| 0.2-0.4 | 13 | 0.31 | 0.62 |
| 0.4-0.6 | 21 | 0.47 | 0.62 |
| 0.6-0.8 | 19 | 0.69 | 0.74 |
| 0.8-1.0 | 32 | 0.88 | 1.00 |

### Latency

p50 0 ms, p95 0 ms, n=970.
