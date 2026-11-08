"""Fine-tunes a small open-source classifier on the labelled corpus. Evaluates on calls held out from training."""
import hashlib, json, random, sqlite3, time, torch
from transformers import AutoTokenizer, AutoModelForSequenceClassification
torch.cuda.set_per_process_memory_fraction(0.075, 0)
BASE = "distilroberta-base"; OUT = "/lg/model"; MAXLEN = 192; TRAIN_CASES = 24000; EPOCHS = 2; WINDOW = 6
random.seed(11); torch.manual_seed(11)
db = sqlite3.connect("file:/data/corpus.db?immutable=1", uri=True); db.row_factory = sqlite3.Row
def take(where, n): return [dict(r) for r in db.execute(f"select case_id,source,channel,scam,hard_negative,payload from cases where label_quality='exact' and {where} order by rand limit ?", (n,))]
rows = take("scam=1", TRAIN_CASES // 2 + 3000) + take("scam=0 and hard_negative=1", TRAIN_CASES // 4 + 1500) + take("scam=0 and hard_negative=0", TRAIN_CASES // 4 + 1500)
holdout = lambda c: int(hashlib.sha256(c.encode()).hexdigest(), 16) % 100 < 15
def lines(r):
    return [f"{e.get('speaker','message')}: {e['text']}" for e in json.loads(r["payload"]).get("events", []) if e.get("text")]
def windows(ls):
    return ["\n".join(ls[max(0, end - WINDOW):end])[-1800:] for end in range(1, len(ls) + 1)]
train, test = [], []
for r in rows:
    ls = lines(r)
    if not ls: continue
    w = windows(ls)
    if holdout(r["case_id"]): test.append((w, r)); continue
    y = int(r["scam"])
    # A scam call starts out looking normal, so only its later windows are labeled dangerous.
    picks = w[len(w) // 2:] if y and len(w) > 1 else w
    for t in random.sample(picks, min(3, len(picks))): train.append((t, y))
random.shuffle(train)
print("train windows", len(train), "held-out calls", len(test), flush=True)
tok = AutoTokenizer.from_pretrained(BASE); model = AutoModelForSequenceClassification.from_pretrained(BASE, num_labels=2).cuda()
opt = torch.optim.AdamW(model.parameters(), lr=3e-5, weight_decay=0.01); scaler = torch.amp.GradScaler("cuda")
t0 = time.time()
for epoch in range(EPOCHS):
    model.train(); random.shuffle(train); total = 0.0
    for b in range(0, len(train), 16):
        chunk = train[b:b + 16]
        enc = tok([c[0] for c in chunk], truncation=True, max_length=MAXLEN, padding=True, return_tensors="pt").to("cuda")
        y = torch.tensor([c[1] for c in chunk]).cuda(); opt.zero_grad()
        with torch.autocast("cuda", dtype=torch.float16): loss = model(**enc, labels=y).loss
        scaler.scale(loss).backward(); scaler.step(opt); scaler.update(); total += loss.item()
    print(f"epoch {epoch + 1} loss {total / (len(train) / 16):.4f} at {time.time() - t0:.0f}s", flush=True)
model.eval().half(); model.save_pretrained(OUT); tok.save_pretrained(OUT)

@torch.inference_mode()
def score(texts):
    out = []
    for b in range(0, len(texts), 64):
        enc = tok(texts[b:b + 64], truncation=True, max_length=MAXLEN, padding=True, return_tensors="pt").to("cuda")
        out += torch.softmax(model(**enc).logits, 1)[:, 1].tolist()
    return out
start = time.perf_counter(); peak = []; n = 0
for w, r in test:
    s = score(w); n += len(w); peak.append((max(s), r))
secs = time.perf_counter() - start
def auc(pos, neg):
    a = sorted([(s, 1) for s in pos] + [(s, 0) for s in neg]); i = 0; rank = 0.0
    while i < len(a):
        j = i
        while j < len(a) and a[j][0] == a[i][0]: j += 1
        rank += sum((i + j + 1) / 2 for k in range(i, j) if a[k][1]); i = j
    return (rank - len(pos) * (len(pos) + 1) / 2) / (len(pos) * len(neg))
def part(f): return [p for p, r in peak if f(r)]
pos, neg, hard = part(lambda r: r["scam"]), part(lambda r: not r["scam"]), part(lambda r: r["hard_negative"])
print(json.dumps({"frames_per_s": round(n / secs), "held_out_calls": len(peak), "auc": round(auc(pos, neg), 4), "auc_vs_hard_negatives": round(auc(pos, hard), 4)}), flush=True)
for t in (0.2, 0.5, 0.8, 0.9, 0.97):
    print(json.dumps({"threshold": t, "catch": round(sum(p >= t for p in pos) / len(pos), 4), "false_alarm": round(sum(p >= t for p in neg) / len(neg), 4), "hard_negative_false_alarm": round(sum(p >= t for p in hard) / len(hard), 4)}), flush=True)
for src in sorted({r["source"] for _, r in peak}):
    p = part(lambda r: r["source"] == src and r["scam"]); q = part(lambda r: r["source"] == src and not r["scam"])
    print(json.dumps({"source": src, "scam": len(p), "benign": len(q), "auc": round(auc(p, q), 4) if p and q else None}), flush=True)
print("DONE", flush=True)
