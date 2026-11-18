import json, os, re, time, hmac
import boto3

TABLE = boto3.resource("dynamodb", region_name="ap-southeast-2").Table("medguard-lists")
CODE = os.environ.get("REVIEWER_CODE", "")
NEED = 2
ID_RE = re.compile(r"^[A-Za-z0-9_-]{1,64}$")


def out(code, body):
    return {"statusCode": code,
            "headers": {"Content-Type": "application/json"},
            "body": json.dumps(body, default=lambda o: int(o))}


def status_of(item):
    a = item.get("approvals", [])
    if any(x.get("decision") == "changes" for x in a):
        return "changes"
    names = {x["reviewer"].lower() for x in a if x.get("decision") == "approve"}
    return "verified" if len(names) >= NEED else "pending"


def public(item):
    it = dict(item)
    it["status"] = status_of(item)
    return it


def code_ok(given):
    return bool(CODE) and hmac.compare_digest(str(given or ""), CODE)


def clean(s, n):
    return str(s or "").strip()[:n]


def submit(body):
    lid = body.get("id", "")
    name = clean(body.get("name"), 60)
    drugs = body.get("drugs")
    if not ID_RE.match(str(lid)) or not name:
        return out(400, {"error": "bad id or name"})
    if not isinstance(drugs, list) or not (2 <= len(drugs) <= 20):
        return out(400, {"error": "a list needs 2 to 20 medicines"})
    drugs = [clean(d, 80) for d in drugs if clean(d, 80)]
    if len(drugs) < 2:
        return out(400, {"error": "a list needs 2 to 20 medicines"})
    existing = TABLE.get_item(Key={"id": lid}).get("Item")
    if existing:
        return out(200, {"ok": True, "existing": True})
    worst = body.get("worst")
    if worst not in ("Major", "Moderate", "Minor", "Unclassified", "None"):
        worst = None
    TABLE.put_item(Item={"id": lid, "name": name, "drugs": drugs,
                         "owner": clean(body.get("owner"), 40), "worst": worst,
                         "submittedAt": int(time.time() * 1000), "approvals": []})
    return out(200, {"ok": True})


def scan_all():
    items, kw = [], {}
    while True:
        r = TABLE.scan(**kw)
        items += r.get("Items", [])
        if "LastEvaluatedKey" not in r:
            return items
        kw["ExclusiveStartKey"] = r["LastEvaluatedKey"]


def review(lid, body):
    if not ID_RE.match(lid):
        return out(400, {"error": "bad id"})
    if not code_ok(body.get("code")):
        return out(403, {"error": "wrong access code"})
    who = clean(body.get("reviewer"), 40)
    decision = body.get("decision")
    note = clean(body.get("note"), 300)
    if not who or decision not in ("approve", "changes"):
        return out(400, {"error": "bad review"})
    if decision == "changes" and not note:
        return out(400, {"error": "say what should change"})
    item = TABLE.get_item(Key={"id": lid}).get("Item")
    if not item:
        return out(404, {"error": "not found"})
    if item.get("owner", "").lower() == who.lower():
        return out(403, {"error": "you cannot review your own list"})
    appr = [a for a in item.get("approvals", []) if a["reviewer"].lower() != who.lower()]
    appr.append({"reviewer": who, "decision": decision, "note": note,
                 "at": int(time.time() * 1000)})
    TABLE.update_item(Key={"id": lid},
                      UpdateExpression="SET approvals = :a",
                      ExpressionAttributeValues={":a": appr})
    item["approvals"] = appr
    return out(200, {"ok": True, "status": status_of(item)})


def lambda_handler(event, context):
    try:
        method = event["requestContext"]["http"]["method"]
        path = event.get("rawPath", "")
        hdr = {k.lower(): v for k, v in (event.get("headers") or {}).items()}
        qs = event.get("queryStringParameters") or {}
        body = {}
        if event.get("body"):
            body = json.loads(event["body"])
        parts = [p for p in path.split("/") if p]
        if parts and parts[0] == "lists":
            if method == "POST" and len(parts) == 1:
                return submit(body)
            if method == "POST" and len(parts) == 3 and parts[2] == "review":
                return review(parts[1], body)
            if method == "GET" and len(parts) == 1:
                if qs.get("ids"):
                    ids = [i for i in qs["ids"].split(",") if ID_RE.match(i)][:50]
                    found = []
                    for i in ids:
                        it = TABLE.get_item(Key={"id": i}).get("Item")
                        if it:
                            found.append(public(it))
                    return out(200, {"lists": found})
                if qs.get("status") == "pending":
                    if not code_ok(hdr.get("x-reviewer-code")) or not hdr.get("x-reviewer-name", "").strip():
                        return out(403, {"error": "reviewers only"})
                    me = hdr["x-reviewer-name"].strip().lower()
                    pend = [public(i) for i in scan_all() if status_of(i) == "pending"
                            and i.get("owner", "").lower() != me]
                    pend.sort(key=lambda x: x.get("submittedAt", 0))
                    return out(200, {"lists": pend})
        return out(404, {"error": "not found"})
    except Exception as e:
        print("error", repr(e))
        return out(500, {"error": "server error"})
