import csv, json, random, sys, os, re
import boto3
from botocore.config import Config
from concurrent.futures import ThreadPoolExecutor

MODEL_ID = "au.anthropic.claude-sonnet-4-5-20250929-v1:0"
NAME = ["Minor", "Moderate", "Major"]
TEST = len(sys.argv) > 1 and sys.argv[1] == "test"
PER = 2 if TEST else 300
OUT = "llm_test.jsonl" if TEST else "llm_estimates.jsonl"

rows = list(csv.DictReader(open("data/test.csv", newline="")))
by = {0: [], 1: [], 2: []}
for r in rows:
    by[int(r["level"])].append((r["drug_a"], r["drug_b"], int(r["level"])))
rnd = random.Random(0)
sample = []
for k in (0, 1, 2):
    rnd.shuffle(by[k]); sample += by[k][:PER]
rnd.shuffle(sample)

done = set()
if os.path.exists(OUT):
    for line in open(OUT):
        d = json.loads(line); done.add((d["a"], d["b"]))
todo = [s for s in sample if (s[0], s[1]) not in done]
print(f"sample {len(sample)} pairs, already done {len(done)}, to do {len(todo)}", flush=True)

client = boto3.client("bedrock-runtime", region_name="ap-southeast-2",
                      config=Config(retries={"max_attempts": 8, "mode": "adaptive"}))

def ask(item):
    a, b, y = item
    prompt = (f"Two medicines are known to have a drug-drug interaction. Using your general pharmacology knowledge, "
              f"classify the severity of the interaction between {a} and {b} into the category a standard "
              f"drug interaction database such as DDInter would most likely use. "
              f"Answer with exactly one word: Minor, Moderate, or Major.")
    try:
        resp = client.invoke_model(modelId=MODEL_ID, body=json.dumps({
            "anthropic_version": "bedrock-2023-05-31", "max_tokens": 10, "temperature": 0,
            "messages": [{"role": "user", "content": prompt}]}))
        cont = json.loads(resp["body"].read()).get("content") or []
        text = cont[0]["text"] if cont else ""
        m = re.search(r"minor|moderate|major", text, re.I)
        lab = NAME.index(m.group(0).capitalize()) if m else -1
        return {"a": a, "b": b, "true": y, "raw": text, "llm": lab}
    except Exception as e:
        return {"error": str(e)[:300]}

fails = 0
with open(OUT, "a") as f, ThreadPoolExecutor(1) as ex:
    for i, r in enumerate(ex.map(ask, todo), 1):
        if "error" in r:
            fails += 1
            if fails <= 2: print("ERROR:", r["error"], flush=True)
            continue
        f.write(json.dumps(r) + "\n"); f.flush()
        if TEST: print(r["a"], "+", r["b"], "| true:", NAME[r["true"]], "| claude said:", repr(r["raw"]), flush=True)
        elif i % 50 == 0: print(f"  {i}/{len(todo)} done", flush=True)

res = [json.loads(l) for l in open(OUT)]
ok = sum(1 for r in res if r["llm"] == r["true"])
print(f"\nfinished: {len(res)} answered, {fails} failed, unparsed {sum(1 for r in res if r['llm'] == -1)}, accuracy so far {ok / max(1, len(res)):.3f}")
if fails: print("some calls failed: run the same command again to retry only those")
