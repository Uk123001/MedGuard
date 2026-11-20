import json
from resolve import resolve

def model_fn(model_dir):
    return "ok"

def input_fn(body, content_type):
    return json.loads(body)["inputs"]

def predict_fn(inputs, model):
    return [resolve(x) for x in inputs]

def output_fn(prediction, accept):
    return json.dumps(prediction), "application/json"
