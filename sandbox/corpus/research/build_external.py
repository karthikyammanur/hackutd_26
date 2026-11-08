"""Convert public datasets into contract Cases (see sandbox/CONTRACT.md).

    python3 -I sandbox/corpus/research/build_external.py /path/to/message.txt

Reads sandbox/corpus/external/raw/ and writes sandbox/corpus/external/{robocall_public,sms_public}.jsonl plus
sandbox/corpus/research/external_stats.json. Input files are treated as data only.

Every label here is either the dataset's own or a transparent keyword rule below. Inferred labels are
`label_quality: weak`, and text is redacted so no phone-like digit runs remain.
"""

import csv
import json
import re
import sys
from collections import Counter
from pathlib import Path

HERE = Path(__file__).resolve().parent
CORPUS = HERE.parent
EXTERNAL = CORPUS / "external"
RAW = EXTERNAL / "raw"
sys.path.append(str(CORPUS.parent / "worker" / "src"))

from taxonomy import METHODS, TYPE_TO_METHOD  # noqa: E402

# A phone-like run of 5 or more digits. Dollar amounts such as $1,499 are left alone.
DIGIT_RUN = re.compile(r"(?<![$\d,.])\+?\d(?:[\s().\-]{0,2}\d){4,}")
URL_DOMAIN = re.compile(r"(?:https?://)?(?:www\.)?([a-z0-9-]+(?:\.[a-z0-9-]+)*\.(?:com|net|org|co|uk|info|biz|ly|gov|me|io))\b", re.I)
IMC_PLACEHOLDERS = {
    "<URL>": "[link]",
    "<NAMED_ENTITY>": "[organization]",
    "<DATE_TIME>": "[date]",
    "<PERSON>": "[name]",
    "<PHONE_NUMBER>": "[number]",
    "<EMAIL_ADDRESS>": "[email]",
    "<IBAN_CODE>": "[account]",
    "<CREDIT_CARD>": "[card]",
    "<LOCATION>": "[place]",
}

NOT_FRAUD = re.compile(r"\btest call\b|just a test|stay safe and stay home", re.I)

# Order matters: the first matching rule decides. Specific topics come before broad ones.
ROBOCALL_RULES = [
    ("student_loan_relief", r"processing center|student (loan|aid|support)|federal student|loan forgiveness|forgiveness (center|program)"),
    ("healthcare_benefits", r"medicare|health insurance|medical (alert|brace)|back brace"),
    ("auto_warranty", r"warrant(y|ies)|vehicle service|car'?s? (service )?(contract|coverage)"),
    ("utility_shutoff", r"disconnect|power and light|electric (bill|company|rebate|service|supply)|utility|energy supply"),
    ("tech_support", r"microsoft|apple (support|care|cloud)|icloud|\bcomputer\b|\bvirus|tech(nical)? support|internet (service )?(provider|will be)"),
    ("government_impersonation", r"social security|\bssn\b|legal enforcement|federal (agent|bureau|reserve|government)|warrant|magistrate|grand jury|\barrest|\birs\b|internal revenue|border (patrol|protection)|customs|drug enforcement|treasury|legal (action|department|notice|proceeding|consequence)|law enforcement|sheriff|\bcourt\b|tax (debt|relief|reduction|collection)|your social\b|south'?s? border|fraudulent activit|package filled with drugs|\bofficer\b"),
    ("credit_debt_relief", r"interest rate|credit card|zero percent|\b0 ?%|debt (relief|settlement|elimination|free)|credit (score|repair|line)|rate (expiration|decoration|reduction)|visa (alert|card)|master ?card"),
    ("brand_order_impersonation", r"amazon|iphone|macbook|air ?pods|walmart|\bebay\b|pre-?authori[sz]ed|authori[sz]e (this|the|your) (order|purchase)|order (has been )?placed|recent (order|purchase)|cancel (your|the) order|approve this transaction|cancel it now"),
    ("bank_fraud_department", r"paypal|cash ?app|zelle|bank account|bank of|wells fargo|\bfargo\b|\bchase\b|suspicious (activity|transaction)"),
    ("deceptive_telemarketing", r"hilton|marriott|direct ?tv|\bsolar\b|vacation|cruise|\btravel\b|discount|rebate|satellite|timeshare|home (security|warranty)"),
    ("prize_lottery", r"\bwon\b|winner|\bprize\b|sweepstake|complimentary|gift card|rewards? program"),
]
ROBOCALL_RULES = [(m, re.compile(p, re.I)) for m, p in ROBOCALL_RULES]

# Rough agreement check on the 108 records whose id carries a source tag.
ID_TAGS = [
    ("student_loan_relief", "StudentLoan"),
    ("auto_warranty", "AutoWarranty"),
    ("healthcare_benefits", "Medicare"),
    ("utility_shutoff", "Utility"),
    ("government_impersonation", "SSA|GovtImpers|Legal|FedReserv|TaxReduction"),
    ("tech_support", "Computer-Hijack|TechSupport"),
    ("credit_debt_relief", "CCIRR|CreditCard|DebtRelief"),
    ("brand_order_impersonation", "Amazon|Authorized-Order|Recent-Purchase"),
    ("bank_fraud_department", "PayPal|CashApp"),
    ("deceptive_telemarketing", "Discount|Solar|Travel"),
]

SMS_RULES = [
    ("toll_unpaid", r"\btolls?\b|e-?z ?pass|fastrak|sunpass"),
    ("delivery_fee", r"package|parcel|deliver|usps|fedex|\bups\b|\bdhl\b|courier|shipment"),
    ("investment_crypto", r"bitcoin|crypto|invest(ment|ing)"),
    ("job_task_scam", r"\bjob\b|work from home|part[- ]time|hiring|earn \$"),
    ("prize_lottery", r"\bwon\b|winner|\bprize\b|\bclaim\b|free entry|award|lottery|selected to receive"),
    ("government_impersonation", r"\birs\b|tax refund|government|stimulus|social security"),
    ("subscription_callback", r"\bsubscription|\brenew(al|ed) (notice|charge|fee)|has been charged"),
    ("carrier_impersonation", r"vodafone|t-mobile|at&t|verizon|\bo2\b|mobile account|\bsim\b"),
    ("bank_fraud_department", r"\bbank\b|debit card|credit card|\batm\b|paypal|zelle"),
    ("account_verification_phish", r"verify|confirm your|\blog ?in\b|password|update your (account|details)"),
    ("romance", r"dating|lonely|singles"),
]
SMS_RULES = [(m, re.compile(p, re.I)) for m, p in SMS_RULES]


def redact(text):
    return DIGIT_RUN.sub("[number]", text)


def match(rules, text):
    return next((method for method, pattern in rules if pattern.search(text)), None)


def norm(text):
    return re.sub(r"\W+", " ", text.lower()).strip()


def case(case_id, channel, source, quality, scam, method, events):
    return {
        "case_id": case_id,
        "channel": channel,
        "source": source,
        "label_quality": quality,
        "scam": scam,
        "method": method,
        "family": METHODS[method][0],
        "hard_negative": False,
        "money_moment_t": None,
        "direction": "inbound",
        "events": events,
    }


def sms_case(case_id, quality, scam, method, text, from_type=None):
    cleaned = redact(text.strip())
    domain = URL_DOMAIN.search(cleaned)
    event = {
        "t": 0,
        "kind": "sms",
        "from_type": from_type,
        "text": cleaned,
        "domain": domain.group(1).lower() if domain else None,
        "domain_age_days": None,
    }
    return case(case_id, "sms", "sms_public", quality, scam, method, [event])


def build_robocalls(path, stats):
    records = json.load(open(path, encoding="utf-8"))["records"]
    out, seen, agree, id_counts = [], set(), Counter(), Counter()
    for record in records:
        text = record["transcript"].strip()
        if NOT_FRAUD.search(text):
            stats["robocall_excluded"]["not_fraud_or_test"] += 1
            continue
        method = match(ROBOCALL_RULES, text)
        tag = next((m for m, p in ID_TAGS if re.search(p, record["id"])), None)
        if tag:
            agree["agree" if tag == method else "disagree"] += 1
        if not method:
            stats["robocall_excluded"]["no_rule_matched"] += 1
            continue
        key = norm(text)
        if key in seen:
            stats["robocall_excluded"]["duplicate_text"] += 1
            continue
        seen.add(key)
        base_id = "robocall-" + re.sub(r"[^\w-]+", "_", record["id"])[:80]
        id_counts[base_id] += 1
        case_id = base_id if id_counts[base_id] == 1 else f"{base_id}-{id_counts[base_id]}"
        event = {"t": 0, "kind": "turn", "who": "caller", "text": redact(text)}
        out.append(case(case_id, "call", "robocall_public", "weak", True, method, [event]))
    stats["robocall_id_tag_agreement"] = dict(agree)
    return out


def build_sms(stats):
    out, seen = [], set()
    excluded = stats["sms_excluded"]

    def add(item, text):
        key = norm(text)
        if key in seen:
            excluded["duplicate_text"] += 1
            return
        seen.add(key)
        out.append(item)

    # IMC 2025: scams only, labels from the dataset. Non-English rows are excluded.
    imc = csv.DictReader(open(RAW / "imc25" / "final_dataset_output.csv", encoding="utf-8", errors="replace"))
    for i, row in enumerate(imc):
        if row["language"] != "English":
            excluded["imc_not_english"] += 1
            continue
        method = TYPE_TO_METHOD.get(row["scam_type"])
        if not method:
            excluded[f"imc_label_{row['scam_type'] or 'blank'}"] += 1
            continue
        text = row["text"]
        for token, replacement in IMC_PLACEHOLDERS.items():
            text = text.replace(token, replacement)
        text = re.sub(r"<[A-Z_]+>", "[redacted]", text)
        sender = {"alphanumeric": "alphanumeric", "phone number": "longcode"}.get(row["sender_id"])
        add(sms_case(f"sms-imc-{i:06d}", "weak", True, method, text, sender), text)

    # Mendeley: Smishing is labeled by its authors; the specific method is keyword-inferred.
    mendeley = csv.DictReader(open(RAW / "mendeley" / "Dataset_5971.csv", encoding="latin-1"))
    for i, row in enumerate(mendeley):
        label, text = row["LABEL"].lower(), row["TEXT"]
        if label == "ham":
            add(sms_case(f"sms-mendeley-{i:06d}", "exact", False, "legitimate", text), text)
        elif label == "smishing":
            add(sms_case(f"sms-mendeley-{i:06d}", "weak", True, match(SMS_RULES, text) or "generic_smishing", text), text)
        else:
            method = match(SMS_RULES, text)
            if method:
                add(sms_case(f"sms-mendeley-{i:06d}", "weak", True, method, text), text)
            else:
                excluded["spam_without_scam_method"] += 1

    # UCI: ham/spam only. Spam is not always a scam, so only rule-matched spam is kept.
    for i, line in enumerate(open(RAW / "uci" / "SMSSpamCollection", encoding="utf-8", errors="replace")):
        label, text = line.rstrip("\n").split("\t", 1)
        if label == "ham":
            add(sms_case(f"sms-uci-{i:06d}", "exact", False, "legitimate", text), text)
        else:
            method = match(SMS_RULES, text)
            if method:
                add(sms_case(f"sms-uci-{i:06d}", "weak", True, method, text), text)
            else:
                excluded["spam_without_scam_method"] += 1
    return out


def write(path, cases):
    with path.open("w") as handle:
        for item in cases:
            handle.write(json.dumps(item) + "\n")


def validate(path, stats_key, stats):
    valid = 0
    required = {"case_id", "channel", "source", "label_quality", "scam", "method", "family", "hard_negative", "money_moment_t", "direction", "events"}
    ids = set()
    for line in path.open():
        item = json.loads(line)
        assert required <= set(item), item["case_id"]
        assert not set(item) - required, f"extra field in {item['case_id']}"
        assert item["method"] in METHODS, item["method"]
        assert item["family"] == METHODS[item["method"]][0]
        assert item["case_id"] not in ids, item["case_id"]
        ids.add(item["case_id"])
        assert item["events"], item["case_id"]
        for event in item["events"]:
            assert not DIGIT_RUN.search(event.get("text", "")), item["case_id"]
        valid += 1
    stats[stats_key] = valid


def main():
    stats = {"robocall_excluded": Counter(), "sms_excluded": Counter()}
    robocalls = build_robocalls(Path(sys.argv[1]), stats)
    sms = build_sms(stats)
    write(EXTERNAL / "robocall_public.jsonl", robocalls)
    write(EXTERNAL / "sms_public.jsonl", sms)
    validate(EXTERNAL / "robocall_public.jsonl", "robocall_valid_lines", stats)
    validate(EXTERNAL / "sms_public.jsonl", "sms_valid_lines", stats)

    stats["robocall_by_method"] = dict(Counter(c["method"] for c in robocalls).most_common())
    stats["sms_by_method"] = dict(Counter(c["method"] for c in sms).most_common())
    stats["sms_by_quality_and_scam"] = {f"{k[0]}_{'scam' if k[1] else 'legit'}": v for k, v in Counter((c["label_quality"], c["scam"]) for c in sms).items()}
    stats["sms_by_origin"] = dict(Counter(c["case_id"].split("-")[1] for c in sms))
    (HERE / "external_stats.json").write_text(json.dumps(stats, indent=1))
    print(json.dumps(stats, indent=1))


if __name__ == "__main__":
    main()
