import boto3

table = boto3.resource("dynamodb", region_name="ap-southeast-2").Table("dinter_interactions")

def lambda_handler(event, context):
    keys = event.get("pair_keys", [])
    results = []
    for k in keys:
        item = table.get_item(Key={"pair_key": k}).get("Item")
        results.append({"pair_key": k, "found": item is not None, "record": item})
    return {"results": results}