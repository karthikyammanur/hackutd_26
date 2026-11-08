"""Scam methods the sandbox classifies. Each entry cites where the method is publicly documented.

See sandbox/corpus/research/sources.md for how each source was retrieved.
"""

FTC_TEXTS = "https://www.ftc.gov/news-events/data-visualizations/data-spotlight/2025/04/top-text-scams-2024"
FTC_IMPOSTER = "https://ftc.gov/news-events/news/press-releases/2026/06/ftc-data-show-people-reported-losing-3-point-5-billion-imposter-scams-2025"
FTC_PHISHING = "https://consumer.ftc.gov/all-scams/phishing-scams"
FTC_SMS = "https://consumer.ftc.gov/articles/how-recognize-and-report-spam-text-messages"
FTC_PHONE = "https://consumer.ftc.gov/articles/phone-scams"
FTC_ROBOCALLS = "https://consumer.ftc.gov/features/robocall-scam-examples"
FTC_MOVE_MONEY = "https://consumer.ftc.gov/consumer-alerts/2024/03/never-move-your-money-protect-it-thats-scam"
FTC_VOICE = "https://consumer.ftc.gov/consumer-alerts/2023/03/scammers-use-ai-enhance-their-family-emergency-schemes"
FTC_UTILITY = "https://consumer.ftc.gov/articles/scammers-pretend-be-your-utility-company"
FTC_DEBT = "https://consumer.ftc.gov/articles/fake-abusive-debt-collectors"
FTC_BOSS = "https://consumer.ftc.gov/consumer-alerts/2026/01/no-thats-not-your-boss-asking-you-buy-gift-cards"
FTC_MEDICARE = "https://consumer.ftc.gov/consumer-alerts/2025/09/medicare-open-enrollment-season-learn-how-protect-yourself-scams"
FTC_CALLBACK = "https://consumer.ftc.gov/consumer-alerts/2018/02/phishers-send-fake-invoices"
FTC_TECH = "https://consumer.ftc.gov/articles/how-spot-avoid-and-report-tech-support-scams"
FTC_CODE = "https://consumer.ftc.gov/consumer-alerts/2024/03/whats-verification-code-why-would-someone-ask-me-it"
FTC_SIM = "https://consumer.ftc.gov/consumer-alerts/2019/10/sim-swap-scams-how-protect-yourself"
FTC_FAKE_CHECK = "https://consumer.ftc.gov/articles/how-spot-avoid-and-report-fake-check-scams"
FTC_RENTAL = "https://consumer.ftc.gov/articles/rental-listing-scams"
FTC_ROMANCE = "https://consumer.ftc.gov/articles/what-know-about-romance-scams"
FTC_JOBS = "https://consumer.ftc.gov/articles/job-scams"
FTC_WARRANTY = "https://consumer.ftc.gov/consumer-alerts/2023/03/what-know-about-auto-service-contracts-extended-warranty-scams"
FBI_PHANTOM = "https://www.fbi.gov/news/podcasts/inside-the-fbi-podcast-the-phantom-hacker-scam"
FBI_ATO = "https://www.fbi.gov/investigate/cyber/alerts/2025/account-takeover-fraud-via-impersonation-of-financial-institution-support"
FBI_QR = "https://www.fbi.gov/contact-us/field-offices/elpaso/news/fbi-tech-tuesday-building-a-digital-defense-against-qr-code-scams"
FCC_GLOSSARY = "https://www.fcc.gov/scam-glossary"
FCC_FRAUD = "https://www.fcc.gov/cell-phone-fraud"
TMOBILE_SCAMS = "https://www.t-mobile.com/dialed-in/tips-tricks/avoid-phone-scams"
UK_SURVEY = "https://www.royalgreenwich.gov.uk/news/2026/phone-scam-uses-ai-clone-victims-voices"
IMC25_DATASET = "https://github.com/reportsmishing/Smishing-Dataset-IMC25"

# id -> (family, description used by Jev, public source)
METHODS = {
    "bank_fraud_department": ("impersonation", "Poses as a bank's fraud team to get codes or move money to a 'safe' account", FTC_MOVE_MONEY),
    "text_then_call_fraud_alert": ("impersonation", "A fake fraud-alert text gets a reply, then a caller posing as the fraud department takes over", FTC_TEXTS),
    "phantom_hacker": ("impersonation", "Staged handoff between fake tech support, fake bank and fake government agent to move savings", FBI_PHANTOM),
    "government_impersonation": ("impersonation", "Poses as police, courts or a tax or benefits agency, threatening arrest or fines", FTC_PHONE),
    "carrier_impersonation": ("impersonation", "Poses as the phone carrier offering refunds or asking for account PINs or codes", TMOBILE_SCAMS),
    "brand_order_impersonation": ("impersonation", "Claims a suspicious order or charge from a well-known retailer and pushes the victim to press a key or call", FTC_ROBOCALLS),
    "tech_support": ("impersonation", "Fake tech support claiming a device problem and asking for remote access or payment", FTC_TECH),
    "utility_shutoff": ("impersonation", "Poses as a utility threatening immediate shutoff unless paid now", FTC_UTILITY),
    "family_emergency_voice_clone": ("impersonation", "Poses as a relative in an emergency, possibly with a cloned voice, asking for money", FTC_VOICE),
    "family_emergency_text": ("impersonation", "Text claiming to be a child or relative on a new number who urgently needs money", IMC25_DATASET),
    "executive_or_coworker": ("impersonation", "Poses as a boss or coworker urgently asking for payments, gift cards or credentials", FTC_BOSS),
    "healthcare_benefits": ("impersonation", "Poses as Medicare, insurance or a health program to get personal data or payment", FTC_MEDICARE),
    "debt_collection": ("impersonation", "Fake debt collector demanding immediate payment for a debt that is invented or unverified", FTC_DEBT),
    "delivery_fee": ("payment_lure", "Claims a package problem and asks for a small fee or card details", FTC_TEXTS),
    "toll_unpaid": ("payment_lure", "Claims an unpaid toll and pushes a payment link", FTC_TEXTS),
    "refund_overpayment": ("payment_lure", "Claims a refund or overpayment and asks for gift cards or money back", FTC_TECH),
    "prize_lottery": ("payment_lure", "Claims a prize or reward that needs a fee or personal details to claim", FTC_PHONE),
    "subscription_callback": ("payment_lure", "Fake renewal or charge notice that pushes the victim to call a scam number", FTC_CALLBACK),
    "student_loan_relief": ("payment_lure", "Promises student loan forgiveness or relief in exchange for fees or account details", FTC_ROBOCALLS),
    "credit_debt_relief": ("payment_lure", "Promises lower card rates, credit repair or debt relief for an upfront fee", FTC_PHONE),
    "advance_fee_loan": ("payment_lure", "Guarantees a loan or credit card in exchange for an upfront payment", FTC_PHONE),
    "auto_warranty": ("payment_lure", "Pressures the victim to buy or renew an overpriced or worthless car service contract", FTC_WARRANTY),
    "deceptive_telemarketing": ("payment_lure", "Illegal sales calls using free trials, discounts or travel offers that lead to fees or recurring charges", FTC_PHONE),
    "one_ring_wangiri": ("payment_lure", "A very short call designed to make the victim call back an expensive international number", FCC_GLOSSARY),
    "account_verification_phish": ("credential_theft", "Urges the victim to verify an account or login through a link", FTC_PHISHING),
    "generic_smishing": ("credential_theft", "Unsolicited text with a link or reply prompt seeking data or money, where the specific lure is unclear", FTC_SMS),
    "qr_code_phish": ("credential_theft", "A QR code that leads to a fake site or malicious payment page", FBI_QR),
    "sim_swap_port_out": ("credential_theft", "Tries to get carrier PINs or approvals to move the victim's number", FTC_SIM),
    "otp_interception": ("credential_theft", "Automated or live call pressing the victim to enter or read a just-sent code", FBI_ATO),
    "survey_voice_harvest": ("credential_theft", "Harmless-sounding survey collecting personal data or voice samples for later fraud", UK_SURVEY),
    "job_task_scam": ("relationship_or_opportunity", "Unsolicited job offer with easy tasks that later requires the victim to pay", FTC_TEXTS),
    "investment_crypto": ("relationship_or_opportunity", "Promises investment or crypto returns and steers money to a fake platform", FTC_PHONE),
    "wrong_number_romance": ("relationship_or_opportunity", "Starts with a mistaken text or romance to build trust before asking for money", FTC_TEXTS),
    "romance": ("relationship_or_opportunity", "Builds a romantic relationship online, then invents urgent needs for money", FTC_ROMANCE),
    "charity_disaster": ("relationship_or_opportunity", "Fake charity or disaster relief pressing for immediate donations", FTC_PHONE),
    "marketplace_rental": ("relationship_or_opportunity", "Fake buyer, seller or landlord asking for deposits, codes or overpayment refunds", FTC_FAKE_CHECK),
    "legitimate": ("none", "A normal, legitimate conversation or message with no scam", ""),
}

# How each dataset label maps to a method. Anything starting with "benign" or "legit" is legitimate.
TYPE_TO_METHOD = {
    # team datagen call and SMS types
    "bank_safe_account": "bank_fraud_department",
    "bank_lock": "bank_fraud_department",
    "grandparent_voice_clone": "family_emergency_voice_clone",
    "fake_carrier_support": "carrier_impersonation",
    "carrier_refund": "carrier_impersonation",
    "gift_card_refund": "refund_overpayment",
    "government_threat": "government_impersonation",
    "tech_support": "tech_support",
    "crypto_investment": "investment_crypto",
    "delivery_fee": "delivery_fee",
    "toll_unpaid": "toll_unpaid",
    "account_verify": "account_verification_phish",
    "job_offer": "job_task_scam",
    "wrong_number_romance": "wrong_number_romance",
    "prize": "prize_lottery",
    # IMC 2025 smishing dataset scam_type values
    "banking": "bank_fraud_department",
    "delivery": "delivery_fee",
    "government": "government_impersonation",
    "telecom": "carrier_impersonation",
    "wrong number": "wrong_number_romance",
    "hey mum/dad": "family_emergency_text",
}


def method_for(call_type: str, scam: bool) -> str:
    if not scam:
        return "legitimate"
    return TYPE_TO_METHOD.get(call_type, call_type if call_type in METHODS else "unmapped")
