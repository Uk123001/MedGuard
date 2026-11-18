import csv, json, os, time
import boto3
from botocore.config import Config
MODEL_ID = "au.anthropic.claude-sonnet-4-5-20250929-v1:0"
client = boto3.client("bedrock-runtime", region_name="ap-southeast-2",
                      config=Config(read_timeout=60, retries={"max_attempts": 8, "mode": "adaptive"}))
OUT = "baseline_results.jsonl"
rows = list(csv.DictReader(open("testset.csv", newline="")))
done = set()
if os.path.exists(OUT):
    for l in open(OUT):
        d = json.loads(l)
        done.add((d["drug_a"], d["drug_b"]))
todo = [r for r in rows if (r["drug_a"], r["drug_b"]) not in done]
print(f"{len(rows)} pairs, {len(done)} done, {len(todo)} to do", flush=True)
PROMPT = ("You are explaining drug interaction results to a user. Explain what is known about the interaction, "
          "if any, between {a} and {b}, including how severe it is (Major, Moderate or Minor) if there is one.\n\n"
          "Write a short, clear explanation (a few sentences).")
for i, r in enumerate(todo, 1):
    for attempt in range(3):
        try:
            resp = client.invoke_model(modelId=MODEL_ID, body=json.dumps({
                "anthropic_version": "bedrock-2023-05-31", "max_tokens": 400,
                "messages": [{"role": "user", "content": PROMPT.format(a=r["drug_a"], b=r["drug_b"])}]}))
            cont = json.loads(resp["body"].read()).get("content") or []
            text = cont[0]["text"] if cont else ""
            rec = {"drug_a": r["drug_a"], "drug_b": r["drug_b"], "truth": r["truth"], "answer": text}
            open(OUT, "a").write(json.dumps(rec) + "\n")
            print(f"  {i}/{len(todo)} ok {r['truth']}", flush=True)
            break
        except Exception as e:
            print(f"  {i}/{len(todo)} attempt {attempt + 1} failed: {str(e)[:150]}", flush=True)
            time.sleep(8)
    time.sleep(1)
print("finished:", sum(1 for _ in open(OUT)), "saved", flush=True)
