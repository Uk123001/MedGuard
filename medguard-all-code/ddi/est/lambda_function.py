import json, os, re
import concurrent.futures as cf
import boto3
from botocore.config import Config

MODEL_ID = "au.anthropic.claude-sonnet-4-5-20250929-v1:0"
NAME = ["Minor", "Moderate", "Major"]
W = json.load(open(os.path.join(os.path.dirname(os.path.abspath(__file__)), "ddi_weights.json")))
IDX = {d: i for i, d in enumerate(W["drugs"])}
client = boto3.client("bedrock-runtime", region_name="ap-southeast-2",
                      config=Config(read_timeout=18, connect_timeout=5,
                                    retries={"max_attempts": 2, "mode": "standard"}))

def lin(x, w, b):
    return [sum(wi * xi for wi, xi in zip(row, x)) + bi for row, bi in zip(w, b)]

def relu(v):
    return [t if t > 0 else 0.0 for t in v]

def predict(a, b):
    ia, ib = IDX.get(a), IDX.get(b)
    if ia is None or ib is None:
        return None
    ea, eb = W["emb"][ia], W["emb"][ib]
    x = [p + q for p, q in zip(ea, eb)] + [p * q for p, q in zip(ea, eb)] + [abs(p - q) for p, q in zip(ea, eb)]
    o = lin(relu(lin(relu(lin(x, W["l1_w"], W["l1_b"])), W["l2_w"], W["l2_b"])), W["l3_w"], W["l3_b"])
    o[2] += W["bias"]
    return max(range(3), key=lambda k: o[k])

PROMPT = """You are helping a user understand a possible drug interaction that is NOT in the verified database. Everything you write will be shown under a banner saying it is an unverified AI estimate.

Drugs: {a} and {b}
A statistical model's severity guess, relevant only if an interaction exists: {level}. This guess is unverified and may be wrong, so do not treat it as fact.

Write exactly four sections. Each starts with its plain heading on its own line, with no markdown symbols (no asterisks, no #):
Why caution
Possible effects
Why this matters
What to do

Rules:
- Begin "Why caution" by saying whether you know of a well-established interaction between these two drugs. If you do not, say so plainly, add that this does not mean the combination is safe, and mention only general, well-established properties of each drug that could matter when combined.
- "Possible effects": up to 3 short lines, each starting with "- ". List only effects that would arise from these two drugs acting on each other. Never list a drug's own separate side effects, and never mention kidney or liver changes, dose adjustments or monitoring. If no such effect is well established, write "- No specific effects are well established".
- "Why this matters": one sentence consistent with the estimate. If you believe the real risk is higher than the estimate, say so.
- "What to do": always say not to start, stop or change any medicine on your own, and to ask a physician or pharmacist before taking these together. Give no other instruction, dose, schedule, or advice to avoid specific foods, drinks or products.
- Never say the combination is safe, harmless or fine. Do not invent numbers or studies. Use hedged wording such as "may" and "can". Keep it under 150 words."""

def explain(e):
    resp = client.invoke_model(modelId=MODEL_ID, body=json.dumps({
        "anthropic_version": "bedrock-2023-05-31", "max_tokens": 400, "temperature": 0,
        "messages": [{"role": "user", "content": PROMPT.format(a=e["drug_a"], b=e["drug_b"], level=e["level"])}]}))
    cont = json.loads(resp["body"].read()).get("content") or []
    text = (cont[0]["text"] if cont else "").replace("*", "").replace("#", "").strip()
    heads = ["Why caution", "Possible effects", "Why this matters", "What to do"]
    if not all(h in text for h in heads) or "physician or pharmacist" not in text:
        return None
    return text

def lambda_handler(event, context):
    keys = event.get("pair_keys", [])
    max_text = int(event.get("max_text", 3))
    out, todo = {}, []
    for k in keys:
        if "|" not in k:
            continue
        a, b = k.split("|", 1)
        lv = predict(a, b)
        if lv is None:
            continue
        out[k] = {"drug_a": a, "drug_b": b, "level": NAME[lv], "explanation": None}
        todo.append(k)
    todo.sort(key=lambda k: -NAME.index(out[k]["level"]))
    with cf.ThreadPoolExecutor(3) as ex:
        futs = {ex.submit(explain, out[k]): k for k in todo[:max_text]}
        for f in cf.as_completed(futs):
            try:
                out[futs[f]]["explanation"] = f.result()
            except Exception:
                pass
    return {"estimates": out}
