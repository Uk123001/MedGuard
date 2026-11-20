import csv, json, os, re, sys, time, collections
import boto3
from botocore.config import Config

MODEL_ID = "au.anthropic.claude-sonnet-4-5-20250929-v1:0"
client = boto3.client("bedrock-runtime", region_name="ap-southeast-2",
                      config=Config(read_timeout=60, retries={"max_attempts": 8, "mode": "adaptive"}))
COVERED = ("Major", "Moderate", "Minor")
VALID = COVERED + ("RecordedNoSeverity", "NoneOrUnknown", "Unclear")

def load(p):
    return [json.loads(l) for l in open(p)]

T = list(csv.DictReader(open("testset.csv", newline="")))
G = {(r["drug_a"], r["drug_b"]): r for r in load("grounded_results.jsonl")}
B = {(r["drug_a"], r["drug_b"]): r for r in load("baseline_results.jsonl")}
truth = {(r["drug_a"], r["drug_b"]): r["truth"] for r in T}
keys = [(r["drug_a"], r["drug_b"]) for r in T if (r["drug_a"], r["drug_b"]) in G and (r["drug_a"], r["drug_b"]) in B]
print(f"test pairs: {len(T)} | scored (present in both runs): {len(keys)}")
N = len(keys)

PROMPT = """Below is a text written for a user about the drug interaction between {a} and {b}. Answer using only the text.

Text:
\"\"\"{text}\"\"\"

Return only a JSON object with two keys:
"severity": one of "Major", "Moderate", "Minor", "RecordedNoSeverity" (the text says an interaction is recorded but gives no severity level), "NoneOrUnknown" (the text says there is no known interaction, or the pair is not covered, or that it cannot say), "Unclear".
"extra_details": true if the text states specific effects, mechanisms, symptoms or medical advice that go beyond a severity level and a recommendation to consult a professional, otherwise false."""

EX = "extractions.jsonl"
cache = {}
if os.path.exists(EX):
    for l in open(EX):
        d = json.loads(l)
        cache[(d["system"], d["a"], d["b"])] = d

def extract(a, b, text):
    for attempt in range(3):
        try:
            resp = client.invoke_model(modelId=MODEL_ID, body=json.dumps({
                "anthropic_version": "bedrock-2023-05-31", "max_tokens": 80, "temperature": 0,
                "messages": [{"role": "user", "content": PROMPT.format(a=a, b=b, text=text)}]}))
            cont = json.loads(resp["body"].read()).get("content") or []
            raw = cont[0]["text"] if cont else ""
            d = json.loads(re.search(r"\{.*\}", raw, re.S).group(0))
            sev = d.get("severity")
            if sev not in VALID:
                sev = "Unclear"
            return {"severity": sev, "extra": bool(d.get("extra_details")), "raw": raw}
        except Exception:
            time.sleep(5)
    return None

todo = [(s, k) for s, src in (("grounded", G), ("baseline", B)) for k in keys if (s, k[0], k[1]) not in cache]
print(f"extractions to do: {len(todo)}", flush=True)
for i, (s, k) in enumerate(todo, 1):
    src = G if s == "grounded" else B
    r = extract(k[0], k[1], src[k]["answer"])
    if r is None:
        continue
    rec = {"system": s, "a": k[0], "b": k[1], **r}
    open(EX, "a").write(json.dumps(rec) + "\n")
    cache[(s, k[0], k[1])] = rec
    if i % 20 == 0:
        print(f"  {i}/{len(todo)}", flush=True)
    time.sleep(0.5)
if any((s, k[0], k[1]) not in cache for s in ("grounded", "baseline") for k in keys):
    print("Some extractions failed (probably throttling). Run the same command again.")
    sys.exit(1)

def retrieved_label(rec):
    v = rec["verified"][0]
    if v["status"] == "verified":
        lv = (v.get("evidence") or {}).get("level")
        return lv if lv in COVERED else "Unclassified"
    if v["status"] == "verified_unclassified":
        return "Unclassified"
    return "NotCovered"

returned = [k for k in keys if retrieved_label(G[k]) != "NotCovered"]
correct_ret = [k for k in returned if retrieved_label(G[k]) == truth[k]]
cov_truth = [k for k in keys if truth[k] != "NotCovered"]
nc_keys = [k for k in keys if truth[k] == "NotCovered"]
prec = len(correct_ret) / len(returned) if returned else 0.0
rec_ = len(correct_ret) / len(cov_truth) if cov_truth else 0.0
f1 = 2 * prec * rec_ / (prec + rec_) if prec + rec_ else 0.0
nc_ok = sum(1 for k in nc_keys if retrieved_label(G[k]) == "NotCovered")
unres = sum(1 for k in keys for r in G[k]["resolved"] if r["method"] == "no_match")
secs = [G[k]["seconds"] for k in keys if "seconds" in G[k]]
print("\n=== RETRIEVAL (grounded pipeline) ===")
print(f"records returned: {len(returned)} | correct: {len(correct_ret)} | precision {prec:.3f}")
print(f"documented pairs: {len(cov_truth)} | retrieved correctly: {len(correct_ret)} | recall {rec_:.3f} | F1 {f1:.3f}")
print(f"not-covered pairs correctly reported as not covered: {nc_ok}/{len(nc_keys)}")
print(f"drug names the resolver could not match: {unres}/{2 * N}")
if secs:
    print(f"pipeline time per pair: mean {sum(secs) / len(secs):.1f}s, max {max(secs):.1f}s")

def classify(t, s):
    if t in COVERED:
        if s == t: return "correct"
        if s in COVERED: return "wrong_severity"
        if s == "NoneOrUnknown": return "said_none"
        if s == "RecordedNoSeverity": return "lost_severity"
        return "unclear"
    if t == "Unclassified":
        if s == "RecordedNoSeverity": return "correct"
        if s in COVERED: return "invented_severity"
        if s == "NoneOrUnknown": return "said_none"
        return "unclear"
    if s == "NoneOrUnknown": return "correct"
    if s in COVERED or s == "RecordedNoSeverity": return "invented_interaction"
    return "unclear"

HALL = ("wrong_severity", "invented_severity", "invented_interaction")
results = {"n": N, "retrieval": {"precision": prec, "recall": rec_, "f1": f1}}
details = []
for s in ("grounded", "baseline"):
    cats = collections.Counter(); per = collections.defaultdict(collections.Counter)
    extra = 0; maj_lower = 0; maj_n = 0; none_cov = 0; none_maj = 0
    for k in keys:
        e = cache[(s, k[0], k[1])]; t = truth[k]; c = classify(t, e["severity"])
        cats[c] += 1; per[t][c] += 1; extra += int(e["extra"])
        if t == "Major":
            maj_n += 1
            if e["severity"] in ("Moderate", "Minor"): maj_lower += 1
        if t in COVERED and e["severity"] == "NoneOrUnknown":
            none_cov += 1
            if t == "Major": none_maj += 1
        details.append([s, t, k[0], k[1], e["severity"], c, e["extra"]])
    h = sum(cats[c] for c in HALL)
    label = "GROUNDED PIPELINE" if s == "grounded" else "CLAUDE ALONE (no database)"
    print(f"\n=== ANSWERS: {label} ===")
    print(f"matches the database: {cats['correct']}/{N} ({cats['correct'] / N:.1%})")
    print(f"hallucination rate: {h}/{N} ({h / N:.1%})  [wrong severity {cats['wrong_severity']}, invented severity for an unclassified pair {cats['invented_severity']}, invented interaction for a not-covered pair {cats['invented_interaction']}]")
    print(f"said 'no known interaction' for a documented pair: {none_cov} (Major pairs: {none_maj})")
    print(f"true Major pairs described as milder: {maj_lower}/{maj_n}")
    print(f"unclear answers: {cats['unclear']} | lost the severity level: {cats['lost_severity']}")
    print(f"adds effects/mechanisms/advice beyond the database: {extra}/{N} ({extra / N:.1%})")
    print(f"  {'truth':13} {'n':>3} {'correct':>8} {'hallucinated':>13}")
    for t in ("Major", "Moderate", "Minor", "Unclassified", "NotCovered"):
        n_t = sum(per[t].values())
        print(f"  {t:13} {n_t:3d} {per[t]['correct']:8d} {sum(per[t][c] for c in HALL):13d}")
    results[s] = {"correct": cats["correct"], "hallucinations": h, "hallucination_rate": h / N, "accuracy": cats["correct"] / N,
                  "said_none_for_documented": none_cov, "major_described_milder": maj_lower, "major_n": maj_n,
                  "extra_details": extra, "categories": dict(cats)}

json.dump(results, open("results_eval.json", "w"), indent=1)
with open("eval_details.csv", "w", newline="") as f:
    w = csv.writer(f)
    w.writerow(["system", "truth", "drug_a", "drug_b", "extracted_severity", "category", "extra_details"])
    w.writerows(details)
print("\nrows where an answer did not match the database (for your spot check):")
for d in details:
    if d[5] != "correct":
        print(f"  {d[0]:9} truth {d[1]:12} said {d[4]:18} {d[5]:20} {d[2]} + {d[3]}")
print("\nsaved results_eval.json and eval_details.csv")
