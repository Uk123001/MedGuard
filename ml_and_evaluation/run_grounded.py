import csv, json, os, time
import boto3
from botocore.config import Config
lam = boto3.client("lambda", region_name="ap-southeast-2", config=Config(read_timeout=120, retries={"max_attempts": 1}))
OUT = "grounded_results.jsonl"
rows = list(csv.DictReader(open("testset.csv", newline="")))
done = set()
if os.path.exists(OUT):
    for l in open(OUT):
        d = json.loads(l)
        done.add((d["drug_a"], d["drug_b"]))
todo = [r for r in rows if (r["drug_a"], r["drug_b"]) not in done]
print(f"{len(rows)} pairs, {len(done)} done, {len(todo)} to do", flush=True)
for i, r in enumerate(todo, 1):
    for attempt in range(3):
        try:
            t0 = time.time()
            resp = lam.invoke(FunctionName="medguard-orchestrator",
                              Payload=json.dumps({"drugs": [r["drug_a"], r["drug_b"]]}).encode())
            out = json.loads(resp["Payload"].read())
            if resp.get("FunctionError") or "verified" not in out:
                raise Exception(str(out)[:200])
            rec = {"drug_a": r["drug_a"], "drug_b": r["drug_b"], "truth": r["truth"],
                   "seconds": round(time.time() - t0, 1), "resolved": out["resolved"],
                   "verified": out["verified"], "answer": out["answer"]}
            open(OUT, "a").write(json.dumps(rec) + "\n")
            print(f"  {i}/{len(todo)} ok ({rec['seconds']}s) {r['truth']}", flush=True)
            break
        except Exception as e:
            print(f"  {i}/{len(todo)} attempt {attempt + 1} failed: {str(e)[:150]}", flush=True)
            time.sleep(5)
print("finished:", sum(1 for _ in open(OUT)), "saved", flush=True)
