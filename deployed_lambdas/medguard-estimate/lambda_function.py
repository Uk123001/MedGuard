import json, os, re
import concurrent.futures as cf
import boto3
from botocore.config import Config

MODEL_ID = "au.anthropic.claude-haiku-4-5-20251001-v1:0"
NAME = ["Minor", "Moderate", "Major"]
W = json.load(open(os.path.join(os.path.dirname(os.path.abspath(__file__)), "ddi_weights.json")))
IDX = {d: i for i, d in enumerate(W["drugs"])}
client = boto3.client("bedrock-runtime", region_name="ap-southeast-2",
                      config=Config(read_timeout=15, connect_timeout=5,
                                    retries={"max_attempts": 1, "mode": "standard"}))

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

PROMPT = """You are a clinical pharmacology assistant. The medicines {a} and {b} are NOT in the verified interaction database, so there is no recorded result for this pair. Your job is to reason from what you know about each medicine (drug class, how it works, how the body breaks it down, its main effects and side effects) and HYPOTHESIZE what could happen if a person takes them together. Everything you write is shown under a banner saying it is an unverified AI hypothesis.

{guess_line}

Write exactly four sections. Each starts with its plain heading on its own line, with no markdown symbols (no asterisks, no #):
Why caution
Possible effects
Why this matters
What to do

Rules:
- "Why caution": two or three sentences. State plainly that there is no verified record for this pair. Then say in plain words what each medicine does in the body, and where the two could overlap, add up, oppose each other, or affect how the body processes the other.
- "Possible effects": three to five lines, each starting with "- ". Each line is one specific hypothesis about what could happen, with the reason in a few words, for example "- Extra drowsiness, because both can slow the nervous system". Use hedged wording such as "may", "could" or "might". Include effects of either medicine that could plausibly be added to, increased or reduced by the other. If you see no plausible overlap, say that no clear overlap is expected from what is known about the two, but that unknown interactions are still possible.
- Mark anything you are unsure of as speculative. Do not invent studies, statistics or doses, and give no numbers.
- Never say the combination is safe, harmless or fine.
- "Why this matters": one or two sentences on how serious the effects could be if the hypothesis is right, and who might be at higher risk. If a statistical guess is given above, stay consistent with it, but say if you think the real risk could be higher.
- "What to do": always say not to start, stop or change any medicine on your own, and to ask a physician or pharmacist before taking these together. Give no doses or schedules.
Keep the whole answer under 220 words."""

LINES = {
    True: {"guess_line": "A statistical model's severity guess, relevant only if an interaction exists: {level}. This guess is unverified and may be wrong.",
           "matters_rule": "stay consistent with the statistical guess, and say if you believe the real risk could be higher."},
    False: {"guess_line": "No statistical severity guess is available for this pair (one or both names are not in the severity model's vocabulary), so reason only from your pharmacology knowledge and do not state a formal severity level.",
            "matters_rule": "say how serious the effects could be if the hypothesis is right, and that the real effect is not known to this system and must be checked by a physician or pharmacist."},
}

def explain(e):
    resp = client.invoke_model(modelId=MODEL_ID, body=json.dumps({
        "anthropic_version": "bedrock-2023-05-31", "max_tokens": 500,
        "messages": [{"role": "user", "content": PROMPT.format(a=e["drug_a"], b=e["drug_b"], **{k: v.format(level=e["level"]) for k, v in LINES[e["level"] in NAME].items()})}]}))
    result = json.loads(resp["body"].read())
    cont = result.get("content") or []
    text = "".join(b.get("text", "") for b in cont if isinstance(b, dict)).replace("*", "").replace("#", "").strip()
    heads = ["Why caution", "Possible effects", "Why this matters", "What to do"]
    if not all(h in text for h in heads) or "physician or pharmacist" not in text:
        print("estimate text rejected, stop_reason =", result.get("stop_reason"), "| got:", text[:200])
        return None
    return text

def lambda_handler(event, context):
    keys = event.get("pair_keys", [])
    max_text = int(event.get("max_text", 8))
    out, todo = {}, []
    for k in keys:
        if "|" not in k:
            continue
        a, b = k.split("|", 1)
        lv = predict(a, b)
        out[k] = {"drug_a": a, "drug_b": b, "level": NAME[lv] if lv is not None else "Unknown", "explanation": None}
        todo.append(k)
    todo.sort(key=lambda k: -NAME.index(out[k]["level"]) if out[k]["level"] in NAME else 1)
    with cf.ThreadPoolExecutor(8) as ex:
        futs = {ex.submit(explain, out[k]): k for k in todo[:max_text]}
        for f in cf.as_completed(futs):
            try:
                out[futs[f]]["explanation"] = f.result()
            except Exception as ex:
                print("estimate model call failed:", repr(ex))
    return {"estimates": out}
