import json, torch, torch.nn as nn
NAME = ["Minor", "Moderate", "Major"]
ck = torch.load("models/ddi_model.pt", weights_only=False)
drugs, bias = ck["drugs"], ck["bias"]
D = {d: i for i, d in enumerate(drugs)}

class Net(nn.Module):
    def __init__(self, n, dim=64):
        super().__init__()
        self.emb = nn.Embedding(n, dim)
        self.mlp = nn.Sequential(nn.Linear(dim * 3, 256), nn.ReLU(), nn.Dropout(0.3),
                                 nn.Linear(256, 128), nn.ReLU(), nn.Linear(128, 3))
    def forward(self, a, b):
        ea, eb = self.emb(a), self.emb(b)
        return self.mlp(torch.cat([ea + eb, ea * eb, (ea - eb).abs()], 1))

m = Net(len(drugs)); m.load_state_dict(ck["state"]); m.eval()
rows = {}
for line in open("llm_estimates.jsonl"):
    r = json.loads(line); rows[(r["a"], r["b"])] = r
total = len(rows)
rows = [r for r in rows.values() if r["llm"] in (0, 1, 2)]
print(f"pairs sampled and saved: {total}; with a usable Claude answer: {len(rows)}")
A = torch.tensor([D[r["a"]] for r in rows]); B = torch.tensor([D[r["b"]] for r in rows])
with torch.no_grad():
    lg = m(A, B)
lg[:, 2] += bias
model = lg.argmax(1).tolist()
llm = [r["llm"] for r in rows]; ys = [r["true"] for r in rows]
comb = [max(a, b) for a, b in zip(model, llm)]
print("true class counts in this sample:", {NAME[k]: ys.count(k) for k in range(3)})

def show(name, ps):
    cm = [[0] * 3 for _ in range(3)]
    for y, p in zip(ys, ps):
        cm[y][p] += 1
    n = len(ys); acc = sum(cm[i][i] for i in range(3)) / n
    f1s = []; per = []
    for i in range(3):
        tp = cm[i][i]; fp = sum(cm[j][i] for j in range(3)) - tp; fn = sum(cm[i]) - tp
        pr = tp / (tp + fp) if tp + fp else 0.0
        rc = tp / (tp + fn) if tp + fn else 0.0
        f1 = 2 * pr * rc / (pr + rc) if pr + rc else 0.0
        f1s.append(f1); per.append((pr, rc, f1))
    low = (cm[2][0] + cm[2][1]) / sum(cm[2])
    minor_up = (cm[0][1] + cm[0][2]) / sum(cm[0])
    print(f"\n{name}")
    print(f"  accuracy {acc:.3f} | macro F1 {sum(f1s) / 3:.3f} | Major predicted as milder: {low:.3f} | Minor predicted as stronger: {minor_up:.3f}")
    print(f"  {'class':9} {'precision':>9} {'recall':>7} {'F1':>6}")
    for i in range(3):
        print(f"  {NAME[i]:9} {per[i][0]:9.3f} {per[i][1]:7.3f} {per[i][2]:6.3f}")
    print("  confusion matrix (rows = true, columns = predicted):")
    print(f"  {'':9} {'Minor':>7} {'Moderate':>9} {'Major':>7}")
    for i in range(3):
        print(f"  {NAME[i]:9} {cm[i][0]:7d} {cm[i][1]:9d} {cm[i][2]:7d}")
    return dict(accuracy=acc, macro_f1=sum(f1s) / 3, major_predicted_milder=low, confusion=cm)

res = {"n": len(rows), "trained_model": show("trained model (safety-tuned)", model),
       "claude_alone": show("Claude alone", llm), "combined_more_severe": show("combined: the more severe of the two", comb)}
json.dump(res, open("results_combo.json", "w"), indent=1)
print("\nsaved results_combo.json")
