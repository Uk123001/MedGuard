import csv, collections
NAME = ["Minor", "Moderate", "Major"]
def load(p):
    with open(p, newline="") as f:
        r = csv.reader(f); next(r)
        return [(a, b, int(l)) for a, b, l in r]
train, val, test = load("data/train.csv"), load("data/val.csv"), load("data/test.csv")

def metrics(name, ys, ps):
    cm = [[0] * 3 for _ in range(3)]
    for y, p in zip(ys, ps):
        cm[y][p] += 1
    n = len(ys)
    acc = sum(cm[i][i] for i in range(3)) / n
    rows = []
    for i in range(3):
        tp = cm[i][i]
        fp = sum(cm[j][i] for j in range(3)) - tp
        fn = sum(cm[i]) - tp
        pr = tp / (tp + fp) if tp + fp else 0.0
        rc = tp / (tp + fn) if tp + fn else 0.0
        f1 = 2 * pr * rc / (pr + rc) if pr + rc else 0.0
        rows.append((pr, rc, f1))
    macro_f1 = sum(r[2] for r in rows) / 3
    major_total = sum(cm[2])
    major_lower = (cm[2][0] + cm[2][1]) / major_total
    print(f"\n{name}")
    print(f"  accuracy {acc:.3f} | macro F1 {macro_f1:.3f} | Major predicted as milder: {major_lower:.3f}")
    print(f"  {'class':9} {'precision':>9} {'recall':>7} {'F1':>6}")
    for i in range(3):
        print(f"  {NAME[i]:9} {rows[i][0]:9.3f} {rows[i][1]:7.3f} {rows[i][2]:6.3f}")
    print("  confusion matrix (rows = true, columns = predicted):")
    print(f"  {'':9} {'Minor':>7} {'Moderate':>9} {'Major':>7}")
    for i in range(3):
        print(f"  {NAME[i]:9} {cm[i][0]:7d} {cm[i][1]:9d} {cm[i][2]:7d}")

print("pairs: train", len(train), "val", len(val), "test", len(test))
c = collections.Counter(y for _, _, y in train)
print("train class counts:", {NAME[k]: c[k] for k in sorted(c)})
ys = [y for _, _, y in test]

metrics("always Moderate", ys, [1] * len(ys))

tot = collections.defaultdict(float); cnt = collections.Counter()
for a, b, y in train:
    for d in (a, b):
        tot[d] += y; cnt[d] += 1
gm = sum(y for _, _, y in train) / len(train)
mean = lambda d: tot[d] / cnt[d] if cnt[d] else gm
def drug_avg(a, b):
    s = (mean(a) + mean(b)) / 2
    return 2 if s >= 1.5 else (0 if s < 0.5 else 1)
metrics("drug-average rule", ys, [drug_avg(a, b) for a, b, _ in test])

low = sum(1 for a, b, _ in test if cnt[a] < 5 or cnt[b] < 5)
print(f"\ntest pairs involving a drug seen fewer than 5 times in training: {low} ({low / len(test):.1%})")
