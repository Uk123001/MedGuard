import csv, json, random
import boto3
MODEL_ID = "au.anthropic.claude-sonnet-4-5-20250929-v1:0"
NAME = ["Minor", "Moderate", "Major"]
client = boto3.client("bedrock-runtime", region_name="ap-southeast-2")

PROMPT = """You are helping a user understand a possible drug interaction that is NOT in the verified database. Everything you write will be shown under a banner saying it is an unverified AI estimate.

Drugs: {a} and {b}
Estimated severity if they interact (from a statistical model, unverified): {level}

Write four short sections with exactly these headings:
Why caution: 1-2 sentences on what is generally known about how these two drugs or their drug classes can interact. Mention only well-established pharmacology, use words like "may" and "can", and say plainly if you are not aware of a well-established interaction.
Possible effects: up to 3 short bullet points.
Why this matters: one sentence on how seriously to take it, consistent with the estimated severity. If you think the real risk is higher than the estimate, say so.
What to do: always say not to start, stop or change any medicine on your own, and to ask a physician or pharmacist before taking these together.

Rules: never say the combination is safe, harmless or fine. Never give doses, schedules or instructions to stop a medicine. Do not invent numbers or studies. Keep it under 150 words."""

rows = list(csv.DictReader(open("data/test.csv", newline="")))
by = {0: [], 1: [], 2: []}
for r in rows:
    by[int(r["level"])].append(r)
rnd = random.Random(7)
cases = []
for k in (2, 1, 0):
    rnd.shuffle(by[k])
    for r in by[k][:2]:
        cases.append((r["drug_a"], r["drug_b"], NAME[k], "DDInter label: " + NAME[k]))
cases.append(("famotidine", "cetirizine", "Moderate", "hand-picked, probably not documented"))
cases.append(("ethanol", "disulfiram", "Moderate", "hand-picked"))

for a, b, level, note in cases:
    resp = client.invoke_model(modelId=MODEL_ID, body=json.dumps({
        "anthropic_version": "bedrock-2023-05-31", "max_tokens": 400, "temperature": 0,
        "messages": [{"role": "user", "content": PROMPT.format(a=a, b=b, level=level)}]}))
    cont = json.loads(resp["body"].read()).get("content") or []
    print("=" * 70)
    print(f"{a} + {b}  |  estimate given: {level}  |  {note}")
    print("-" * 70)
    print(cont[0]["text"] if cont else "(empty reply)")
