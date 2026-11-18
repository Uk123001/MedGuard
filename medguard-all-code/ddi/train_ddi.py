import csv, json, time, os
import torch, torch.nn as nn, torch.nn.functional as F
torch.manual_seed(0)
NAME = ["Minor", "Moderate", "Major"]

def load(p):
    with open(p, newline="") as f:
        r = csv.reader(f); next(r)
        return [(a, b, int(l)) for a, b, l in r]
train, val, test = load("data/train.csv"), load("data/val.csv"), load("data/test.csv")
drugs = sorted({d for a, b, _ in train + val + test for d in (a, b)})
D = {d: i for i, d in enumerate(drugs)}

def tens(data):
    return (torch.tensor([D[a] for a, _, _ in data]), torch.tensor([D[b] for _, b, _ in data]),
            torch.tensor([y for _, _, y in data]))
Atr, Btr, Ytr = tens(train); Ava, Bva, Yva = tens(val); Ate, Bte, Yte = tens(test)

class Net(nn.Module):
    def __init__(self, n, dim=64):
        super().__init__()
        self.emb = nn.Embedding(n, dim)
        self.mlp = nn.Sequential(nn.Linear(dim * 3, 256), nn.ReLU(), nn.Dropout(0.3),
                                 nn.Linear(256, 128), nn.ReLU(), nn.Linear(128, 3))
    def forward(self, a, b):
        ea, eb = self.emb(a), self.emb(b)
        return self.mlp(torch.cat([ea + eb, ea * eb, (ea - eb).abs()], 1))

def confusion(ys, ps):
    cm = [[0] * 3 for _ in range(3)]
    for y, p in zip(ys, ps):
        cm[y][p] += 1
    return cm

def summarize(cm):
    n = sum(map(sum, cm)); rows = []
    for i in range(3):
        tp = cm[i][i]; fp = sum(cm[j][i] for j in range(3)) - tp; fn = sum(cm[i]) - tp
        pr = tp / (tp + fp) if tp + fp else 0.0
        rc = tp / (tp + fn) if tp + fn else 0.0
        f1 = 2 * pr * rc / (pr + rc) if pr + rc else 0.0
        rows.append((pr, rc, f1))
    acc = sum(cm[i][i] for i in range(3)) / n
    return acc, sum(r[2] for r in rows) / 3, (cm[2][0] + cm[2][1]) / sum(cm[2]), rows

def logits(m, A, B):
    m.eval()
    with torch.no_grad():
        return torch.cat([m(A[i:i + 4096], B[i:i + 4096]) for i in range(0, len(A), 4096)])

def preds(lg, bias=0.0):
    lg = lg.clone(); lg[:, 2] += bias
    return lg.argmax(1).tolist()

def show(name, ys, ps):
    cm = confusion(ys, ps); acc, mf1, low, rows = summarize(cm)
    print(f"\n{name}")
    print(f"  accuracy {acc:.3f} | macro F1 {mf1:.3f} | Major predicted as milder: {low:.3f}")
    print(f"  {'class':9} {'precision':>9} {'recall':>7} {'F1':>6}")
    for i in range(3):
        print(f"  {NAME[i]:9} {rows[i][0]:9.3f} {rows[i][1]:7.3f} {rows[i][2]:6.3f}")
    print("  confusion matrix (rows = true, columns = predicted):")
    print(f"  {'':9} {'Minor':>7} {'Moderate':>9} {'Major':>7}")
    for i in range(3):
        print(f"  {NAME[i]:9} {cm[i][0]:7d} {cm[i][1]:9d} {cm[i][2]:7d}")
    return dict(accuracy=acc, macro_f1=mf1, major_predicted_milder=low, confusion=cm,
                per_class={NAME[i]: dict(precision=rows[i][0], recall=rows[i][1], f1=rows[i][2]) for i in range(3)})

cnt = torch.bincount(Ytr, minlength=3).float()
w = (cnt.sum() / (3 * cnt)) ** 0.5
print("class weights (Minor, Moderate, Major):", [round(x, 2) for x in w.tolist()])
m = Net(len(drugs))
opt = torch.optim.Adam(m.parameters(), lr=2e-3, weight_decay=1e-5)
yva = Yva.tolist(); best, state = -1.0, None
EPOCHS = 25
for ep in range(EPOCHS):
    m.train(); t0 = time.time(); perm = torch.randperm(len(Ytr)); tot = 0.0
    for i in range(0, len(perm), 512):
        idx = perm[i:i + 512]
        opt.zero_grad()
        loss = F.cross_entropy(m(Atr[idx], Btr[idx]), Ytr[idx], weight=w)
        loss.backward(); opt.step(); tot += loss.item() * len(idx)
    _, mf1, low, _ = summarize(confusion(yva, preds(logits(m, Ava, Bva))))
    print(f"  epoch {ep + 1}/{EPOCHS} loss {tot / len(perm):.4f} val_macro_F1 {mf1:.4f} val_Major_milder {low:.3f} ({time.time() - t0:.0f}s)", flush=True)
    if mf1 > best:
        best, state = mf1, {k: v.clone() for k, v in m.state_dict().items()}
m.load_state_dict(state)

lv = logits(m, Ava, Bva)
chosen = None
for b in [i * 0.25 for i in range(0, 25)]:
    _, mf1, low, rows = summarize(confusion(yva, preds(lv, b)))
    if rows[2][1] >= 0.85:
        chosen = b; break
if chosen is None:
    chosen = max([i * 0.25 for i in range(0, 25)], key=lambda b: summarize(confusion(yva, preds(lv, b)))[1])
print(f"\nbest val macro F1 {best:.4f}; safety bias for Major chosen on validation: {chosen}")

lt = logits(m, Ate, Bte); yte = Yte.tolist()
res = {"model": show("trained model (raw)", yte, preds(lt)),
       "model_safety_tuned": show(f"trained model (Major bias +{chosen}, chosen on validation)", yte, preds(lt, chosen)),
       "major_bias": chosen, "params": sum(p.numel() for p in m.parameters())}
json.dump(res, open("results_ddi.json", "w"), indent=1)
os.makedirs("models", exist_ok=True)
torch.save({"state": m.state_dict(), "drugs": drugs, "bias": chosen}, "models/ddi_model.pt")
print("\nparams:", res["params"], "| saved models/ddi_model.pt and results_ddi.json")
