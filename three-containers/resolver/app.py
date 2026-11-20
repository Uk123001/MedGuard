"""MedGuard name resolver microservice.
Cascade: exact match, alias table, RxNorm approximate-term lookup, difflib fuzzy match (cutoff 0.8)."""
import difflib, json, os, urllib.parse, urllib.request
from flask import Flask, jsonify, request

app = Flask(__name__)
HERE = os.path.dirname(os.path.abspath(__file__))
VOCAB = [l.strip().lower() for l in open(os.path.join(HERE, "drugs.txt")) if l.strip()]
VSET = set(VOCAB)
ALIASES = {
    "aspirin": "acetylsalicylic acid", "tylenol": "acetaminophen", "paracetamol": "acetaminophen",
    "advil": "ibuprofen", "motrin": "ibuprofen", "coumadin": "warfarin", "lipitor": "atorvastatin",
    "glucophage": "metformin", "zocor": "simvastatin", "prozac": "fluoxetine", "zoloft": "sertraline",
    "plavix": "clopidogrel", "lasix": "furosemide", "valium": "diazepam", "xanax": "alprazolam",
    "viagra": "sildenafil", "zithromax": "azithromycin", "cipro": "ciprofloxacin",
}
USE_RXNORM = os.environ.get("USE_RXNORM", "1") == "1"
_cache = {}

def rxnorm(term):
    """Ask the public RxNorm service for the closest drug name; None if it is unreachable."""
    if term in _cache:
        return _cache[term]
    out = None
    try:
        u = "https://rxnav.nlm.nih.gov/REST/approximateTerm.json?maxEntries=1&term=" + urllib.parse.quote(term)
        c = json.load(urllib.request.urlopen(u, timeout=3))["approximateGroup"].get("candidate", [])
        if c:
            u2 = "https://rxnav.nlm.nih.gov/REST/rxcui/%s/properties.json" % c[0]["rxcui"]
            name = json.load(urllib.request.urlopen(u2, timeout=3))["properties"]["name"].lower()
            out = next((w for w in [name] + name.split() if w in VSET), None)
    except Exception:
        out = None
    _cache[term] = out
    return out

def resolve(raw):
    s = " ".join(str(raw).strip().lower().split())
    if s in VSET:
        return s, "exact"
    if s in ALIASES:
        return ALIASES[s], "alias"
    if USE_RXNORM:
        r = rxnorm(s)
        if r:
            return r, "rxnorm"
    m = difflib.get_close_matches(s, VOCAB + list(ALIASES), n=1, cutoff=0.8)
    if m:
        return ALIASES.get(m[0], m[0]), "fuzzy"
    return None, "not_found"

@app.get("/health")
def health():
    return jsonify(status="ok", service="resolver", vocabulary=len(VOCAB))

@app.post("/resolve")
def do_resolve():
    names = (request.get_json(silent=True) or {}).get("names", [])
    res = []
    for n in names:
        match, how = resolve(n)
        res.append({"input": n, "match": match, "method": how})
    return jsonify(resolved=res)

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=8080)
