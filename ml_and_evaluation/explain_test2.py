import csv, json, random
import boto3
MODEL_ID = "au.anthropic.claude-sonnet-4-5-20250929-v1:0"
client = boto3.client("bedrock-runtime", region_name="ap-southeast-2")

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
- "Possible effects": up to 3 short lines, each starting with "- ". Only effects that are well established for these drugs or their classes. If none are established, write "- No specific effects are well established".
- "Why this matters": one sentence consistent with the estimate. If you believe the real risk is higher than the estimate, say so.
- "What to do": always say not to start, stop or change any medicine on your own, and to ask a physician or pharmacist before taking these together. Give no other instruction, dose, schedule, or advice to avoid specific foods, drinks or products.
- Never say the combination is safe, harmless or fine. Do not invent numbers or studies. Use hedged wording such as "may" and "can". Keep it under 150 words."""

covered = {r["pair_key"] for r in csv.DictReader(open("ddinter_merged.csv", newline="", encoding="utf-8"))}
names = sorted(json.load(open("/home/cloudshell-user/resolver/drug_vocab.json")))
rnd = random.Random(11)
extra = []
while len(extra) < 2:
    a, b = sorted(rnd.sample(names, 2))
    if "|".join(sorted((a, b))) not in covered and len(a) < 28 and len(b) < 28:
        extra.append((a, b, "Moderate", "random pair NOT in DDInter"))

cases = [("famotidine", "cetirizine", "Moderate", "problem case"),
         ("lidocaine", "phenylbutazone", "Minor", "problem case"),
         ("ethanol", "disulfiram", "Moderate", "problem case")] + extra
for a, b, level, note in cases:
    resp = client.invoke_model(modelId=MODEL_ID, body=json.dumps({
        "anthropic_version": "bedrock-2023-05-31", "max_tokens": 400, "temperature": 0,
        "messages": [{"role": "user", "content": PROMPT.format(a=a, b=b, level=level)}]}))
    cont = json.loads(resp["body"].read()).get("content") or []
    print("=" * 70)
    print(f"{a} + {b}  |  estimate given: {level}  |  {note}")
    print("-" * 70)
    print(cont[0]["text"] if cont else "(empty reply)")
