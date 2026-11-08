"""Safe Signal Guard: Jev-style decisions from small open-source models, on the Nemotron GPU.

The danger score comes from distilroberta fine-tuned on the labeled corpus (train.py). The red-flag
scores come from GLiClass, which has no labels here to be validated against. Call text stays in memory.
"""

import asyncio
import os
import re
import sys

import torch
from fastapi import FastAPI
from gliclass import GLiClassModel, ZeroShotClassificationPipeline
from pydantic import BaseModel, Field
from transformers import AutoModelForSequenceClassification, AutoTokenizer

sys.path.insert(0, "/srv")
from pipeline import FLAGS  # noqa: E402

MODEL_DIR = os.environ.get("GUARD_MODEL_DIR", "/lg/model")
FLAG_MODEL = "knowledgator/gliclass-base-v3.0"
DANGEROUS_AT = float(os.environ.get("GUARD_DANGEROUS_AT", "0.5"))
UNCERTAIN_AT = float(os.environ.get("GUARD_UNCERTAIN_AT", "0.2"))
MAX_LENGTH = 192
MAX_BATCH = 64
GATHER_S = 0.004
CONVERSATION = "MOST RECENT CONVERSATION:\n"
SPEAKER = re.compile(r"^(CALLER|CUSTOMER|MESSAGE):", re.MULTILINE)

torch.cuda.set_per_process_memory_fraction(0.08, 0)
FLAG_LABELS = {flag: value[1] for flag, value in FLAGS.items()}


def conversation_of(state: str) -> str:
    """Reduces the pipeline's state to the same form the model was trained on."""
    if state.startswith("TEXT MESSAGE RECEIVED."):
        return SPEAKER.sub(lambda match: f"{match.group(1).lower()}:", state.split(chr(10) * 2)[-1])[-1800:]
    if CONVERSATION not in state:
        return state[-1800:]
    window = state.split(CONVERSATION, 1)[1]
    return SPEAKER.sub(lambda match: f"{match.group(1).lower()}:", window)[-1800:]


class Models:
    def __init__(self):
        self.tokenizer = AutoTokenizer.from_pretrained(MODEL_DIR)
        self.model = AutoModelForSequenceClassification.from_pretrained(MODEL_DIR).half().cuda().eval()
        flag_model = GLiClassModel.from_pretrained(FLAG_MODEL, torch_dtype=torch.float16)
        flag_tokenizer = AutoTokenizer.from_pretrained(FLAG_MODEL)
        self.flags = ZeroShotClassificationPipeline(flag_model, flag_tokenizer, classification_type="multi-label", device="cuda:0", progress_bar=False)

    @torch.inference_mode()
    def score(self, states: list[str]) -> list[dict]:
        texts = [conversation_of(state) for state in states]
        encoded = self.tokenizer(texts, truncation=True, max_length=MAX_LENGTH, padding=True, return_tensors="pt").to("cuda")
        danger = torch.softmax(self.model(**encoded).logits, 1)[:, 1].tolist()
        flag_rows = self.flags(texts, list(FLAG_LABELS.values()), threshold=0.0, batch_size=len(texts))
        results = []
        for probability, row in zip(danger, flag_rows):
            by_label = {item["label"]: item["score"] for item in row}
            tier = "dangerous" if probability >= DANGEROUS_AT else "uncertain" if probability >= UNCERTAIN_AT else "safe"
            results.append(
                {
                    "tier": tier,
                    "p_dangerous": probability,
                    "p_uncertain": 0.0 if tier == "dangerous" else max(0.0, 1.0 - probability) if tier == "uncertain" else 0.0,
                    "flags": {flag: by_label.get(label, 0.0) for flag, label in FLAG_LABELS.items()},
                }
            )
        return results


class Request(BaseModel):
    state: str = Field(min_length=1, max_length=20000)


app = FastAPI()
models = Models()
queue: asyncio.Queue = asyncio.Queue()


async def batcher():
    """Groups requests that arrive together, which is what makes the GPU fast here."""
    loop = asyncio.get_running_loop()
    while True:
        batch = [await queue.get()]
        deadline = loop.time() + GATHER_S
        while len(batch) < MAX_BATCH and (left := deadline - loop.time()) > 0:
            try:
                batch.append(await asyncio.wait_for(queue.get(), left))
            except TimeoutError:
                break
        try:
            results = await asyncio.to_thread(models.score, [state for state, _ in batch])
            for (_, future), result in zip(batch, results):
                future.set_result(result)
        except Exception as error:  # a bad batch must not stop the loop
            for _, future in batch:
                if not future.done():
                    future.set_exception(error)


@app.on_event("startup")
async def start_batcher():
    app.state.batcher = asyncio.create_task(batcher())


@app.get("/health")
async def health():
    return {"ok": True}


@app.post("/classify")
async def classify(request: Request):
    future = asyncio.get_running_loop().create_future()
    await queue.put((request.state, future))
    return await future
