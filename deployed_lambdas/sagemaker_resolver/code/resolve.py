import os
import json, sys, urllib.parse, urllib.request
from difflib import get_close_matches

BASE = "https://rxnav.nlm.nih.gov/REST"
VOCAB = json.load(open(os.path.join(os.path.dirname(os.path.abspath(__file__)), "drug_vocab.json")))
ALIASES = {"aspirin": "acetylsalicylic acid"}
for _a, _t in ALIASES.items():
    if _t in VOCAB:
        VOCAB[_a] = VOCAB[_t]

def get(url):
    with urllib.request.urlopen(url, timeout=15) as r:
        return json.load(r)

def to_generic(name):
    q = urllib.parse.quote(name)
    data = get(f"{BASE}/approximateTerm.json?term={q}&maxEntries=1")
    cands = data.get("approximateGroup", {}).get("candidate", [])
    if not cands:
        return None
    rxcui = cands[0]["rxcui"]
    rel = get(f"{BASE}/rxcui/{rxcui}/related.json?tty=IN")
    for grp in rel.get("relatedGroup", {}).get("conceptGroup", []):
        for p in grp.get("conceptProperties", []):
            return p["name"]
    props = get(f"{BASE}/rxcui/{rxcui}/properties.json")
    return props.get("properties", {}).get("name")

def resolve(text):
    t = text.strip().lower()
    if t in VOCAB:
        return {"input": text, "id": VOCAB[t], "name": t, "method": "exact"}
    try:
        g = to_generic(t)
    except Exception:
        g = None
    g = g.lower() if g else None
    if g and g in VOCAB:
        return {"input": text, "id": VOCAB[g], "name": g, "method": "rxnorm"}
    for c in [x for x in (g, t) if x]:
        m = get_close_matches(c, VOCAB.keys(), n=1, cutoff=0.8)
        if m:
            return {"input": text, "id": VOCAB[m[0]], "name": m[0], "method": "fuzzy"}
    return {"input": text, "id": None, "name": None, "method": "no_match"}

if __name__ == "__main__":
    for n in sys.argv[1:]:
        print(resolve(n))
