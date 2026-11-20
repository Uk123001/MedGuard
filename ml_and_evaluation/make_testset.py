import csv, random, collections
rnd = random.Random(42)
rows = list(csv.DictReader(open("ddinter_merged.csv", newline="", encoding="utf-8")))
covered = set(r["pair_key"] for r in rows)
by = collections.defaultdict(list)
for r in rows:
    a, b = r["drug_a"].strip(), r["drug_b"].strip()
    if len(a) > 40 or len(b) > 40:
        continue
    by[r["level"]].append((a, b))
quota = {"Major": 12, "Moderate": 12, "Minor": 6, "Unknown": 5}
out = []
for lv, n in quota.items():
    pool = by[lv]
    rnd.shuffle(pool)
    for a, b in pool[:n]:
        out.append((a, b, "Unclassified" if lv == "Unknown" else lv))
names = sorted({x for r in rows for x in (r["drug_a"].strip(), r["drug_b"].strip()) if len(x) <= 40})
nc = 0
while nc < 5:
    a, b = rnd.sample(names, 2)
    if "|".join(sorted((a.lower(), b.lower()))) not in covered:
        out.append((a, b, "NotCovered"))
        nc += 1
rnd.shuffle(out)
with open("testset.csv", "w", newline="") as f:
    w = csv.writer(f)
    w.writerow(["drug_a", "drug_b", "truth"])
    w.writerows(out)
print(len(out), "pairs:", dict(collections.Counter(t for _, _, t in out)))
for a, b, t in out:
    print(f"{t:13} {a} + {b}")
