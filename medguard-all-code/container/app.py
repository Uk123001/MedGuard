from flask import Flask, request, Response
import lambda_function as svc

app = Flask(__name__)


@app.route("/health")
def health():
    return {"status": "ok", "service": "medguard-lists"}


@app.route("/", defaults={"p": ""}, methods=["GET", "POST", "OPTIONS"])
@app.route("/<path:p>", methods=["GET", "POST", "OPTIONS"])
def handle(p):
    event = {
        "requestContext": {"http": {"method": request.method}},
        "rawPath": "/" + p,
        "headers": dict(request.headers),
        "queryStringParameters": request.args.to_dict(),
        "body": request.get_data(as_text=True),
    }
    r = svc.lambda_handler(event, None)
    return Response(r["body"], status=r["statusCode"], mimetype="application/json")
