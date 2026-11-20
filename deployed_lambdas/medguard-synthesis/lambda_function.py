import boto3
import json

bedrock = boto3.client("bedrock-runtime", region_name="ap-southeast-2")

MODEL_ID = "au.anthropic.claude-sonnet-4-6"


def fallback_text(verified_pairs):
    # Used only when the model returns nothing. Built from the database
    # evidence alone, no AI text, no reassurance.
    lines = []
    for p in verified_pairs:
        if p["status"] == "verified":
            ev = p["evidence"]
            lines.append(
                f"{ev['drug_a']} + {ev['drug_b']}: recorded in the DDInter database with {ev['level']} severity."
            )
        elif p["status"] == "verified_unclassified":
            ev = p["evidence"]
            lines.append(
                f"{ev['drug_a']} + {ev['drug_b']}: an interaction is recorded in the DDInter database, but its severity is not classified."
            )
        else:
            names = p["pair_key"].replace("|", " + ")
            lines.append(
                f"{names}: not covered by the DDInter database. This does not mean the combination is safe. Please ask a physician or pharmacist."
            )
    return " ".join(lines)


def synthesize(verified_pairs):
    evidence_lines = []
    for p in verified_pairs:
        if p["status"] == "verified":
            ev = p["evidence"]
            evidence_lines.append(
                f"- {ev['drug_a']} + {ev['drug_b']}: severity = {ev['level']}"
            )
        elif p["status"] == "verified_unclassified":
            ev = p["evidence"]
            evidence_lines.append(
                f"- {ev['drug_a']} + {ev['drug_b']}: interaction recorded in DDInter, but severity is not classified"
            )
        else:
            evidence_lines.append(
                f"- {p['pair_key'].replace('|', ' + ')}: not covered by DDInter ({p['reason']})"
            )

    evidence_text = "\n".join(evidence_lines)

    prompt = f"""You are explaining drug interaction results to a user. Use ONLY the verified evidence below. Do not add any information that is not explicitly stated here. If a pair is "not covered", say so plainly and do not guess at its risk.

Verified evidence:
{evidence_text}

Write a short, clear explanation (a few sentences) covering every pair listed above."""

    for attempt in range(2):
        response = bedrock.invoke_model(
            modelId=MODEL_ID,
            body=json.dumps({
                "anthropic_version": "bedrock-2023-05-31",
                "max_tokens": 400,
                "messages": [{"role": "user", "content": prompt}]
            })
        )
        result = json.loads(response["body"].read())
        blocks = result.get("content") or []
        text = "".join(b.get("text", "") for b in blocks if isinstance(b, dict)).strip()
        if text:
            return text
        print("empty model reply, stop_reason =", result.get("stop_reason"), "attempt", attempt + 1)

    return fallback_text(verified_pairs)


def lambda_handler(event, context):
    v = event.get("verified", [])
    try:
        return {"answer": synthesize(v)}
    except Exception as e:
        print("model call failed, using database facts only:", repr(e))
        return {"answer": fallback_text(v)}
