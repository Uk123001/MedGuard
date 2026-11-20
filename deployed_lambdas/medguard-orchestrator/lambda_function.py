import boto3
import json
from itertools import combinations
from concurrent.futures import ThreadPoolExecutor
from botocore.config import Config

sm = boto3.client("sagemaker-runtime", region_name="ap-southeast-2")
lam = boto3.client("lambda", region_name="ap-southeast-2")
lam_est = boto3.client("lambda", region_name="ap-southeast-2",
                       config=Config(read_timeout=20, connect_timeout=5, retries={"max_attempts": 0}))

ENDPOINT = "medguard-resolver-ep"


def call(fn, payload, client=None):
    r = (client or lam).invoke(FunctionName=fn, Payload=json.dumps(payload).encode())
    out = json.loads(r["Payload"].read())
    if r.get("FunctionError"):
        raise Exception(f"{fn} failed: {out}")
    return out


CANONICAL = {"aspirin": "acetylsalicylic acid"}


def label(d):
    n = (d["name"] or d["input"]).lower().strip()
    return CANONICAL.get(n, n)


def make_pairs(resolved_drugs):
    pairs = []
    for a, b in combinations(resolved_drugs, 2):
        names_sorted = sorted([label(a), label(b)])
        pairs.append({
            "drug_a": a,
            "drug_b": b,
            "pair_key": f"{names_sorted[0]}|{names_sorted[1]}",
        })
    return pairs


def run(event):
    drugs = [d for d in event.get("drugs", []) if str(d).strip()]
    if len(drugs) < 2:
        return {"error": "Please enter at least two drugs."}

    r = sm.invoke_endpoint(
        EndpointName=ENDPOINT,
        ContentType="application/json",
        Body=json.dumps({"inputs": drugs}),
    )
    resolved = json.loads(r["Body"].read())

    unique, seen = [], set()
    for d in resolved:
        k = label(d)
        if k not in seen:
            seen.add(k)
            unique.append(d)
    if len(unique) < 2:
        return {"error": "Please enter at least two different drugs.", "resolved": resolved}

    pairs = make_pairs(unique)
    retrievals = call("medguard-retrieval", {"pair_keys": [p["pair_key"] for p in pairs]})["results"]
    verified = call("medguard-verification", {"pairs": pairs, "retrievals": retrievals})["verified"]

    uncovered = [v["pair_key"] for v in verified if v.get("status") == "not_covered"]

    def get_answer():
        return call("medguard-synthesis", {"verified": verified})["answer"]

    def get_estimates():
        if not uncovered:
            return {}
        try:
            return call("medguard-estimate", {"pair_keys": uncovered, "max_text": 8}, lam_est).get("estimates", {})
        except Exception:
            return {}

    with ThreadPoolExecutor(2) as ex:
        fa = ex.submit(get_answer)
        fe = ex.submit(get_estimates)
        answer = fa.result()
        estimates = fe.result()

    return {"resolved": resolved, "verified": verified, "answer": answer, "estimates": estimates}


def lambda_handler(event, context):
    if "body" in event:
        try:
            event = json.loads(event["body"] or "{}")
        except Exception:
            return {"statusCode": 400, "body": json.dumps({"error": "Invalid request body."})}
        try:
            result = run(event)
        except Exception:
            return {"statusCode": 500, "body": json.dumps({"error": "Something went wrong. Please try again."})}
        return {"statusCode": 200, "headers": {"Content-Type": "application/json"}, "body": json.dumps(result)}
    return run(event)
