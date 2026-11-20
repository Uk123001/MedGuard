def verify_pair(pair_dict, retrieval_result):
    drug_a = pair_dict["drug_a"]
    drug_b = pair_dict["drug_b"]

    # Case 1: one or both drug names never resolved in the first place
    if drug_a["method"] == "no_match" or drug_b["method"] == "no_match":
        return {
            "pair_key": pair_dict["pair_key"],
            "status": "not_covered",
            "reason": "one or both drugs were not recognized",
            "evidence": None,
        }

    # Case 2: both resolved fine, but no record exists for this exact pair
    if not retrieval_result["found"]:
        return {
            "pair_key": pair_dict["pair_key"],
            "status": "not_covered",
            "reason": "no interaction record exists for this pair in DDInter",
            "evidence": None,
        }

    # Case 3: found a record, but DDInter itself doesn't have a severity for it
    level = retrieval_result["record"]["level"]
    if level == "Unknown":
        return {
            "pair_key": pair_dict["pair_key"],
            "status": "verified_unclassified",
            "reason": "interaction is recorded but severity is not classified",
            "evidence": retrieval_result["record"],
        }

    # Case 4: the good case, a real, classified interaction record
    return {
        "pair_key": pair_dict["pair_key"],
        "status": "verified",
        "reason": None,
        "evidence": retrieval_result["record"],
    }


def lambda_handler(event, context):
    pairs = event.get("pairs", [])
    by_key = {r["pair_key"]: r for r in event.get("retrievals", [])}
    missing = {"found": False, "record": None}
    return {"verified": [verify_pair(p, by_key.get(p["pair_key"], missing)) for p in pairs]}