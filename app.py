from flask import Flask, Response, request
import requests

app = Flask(__name__)

# Change this to your panel's actual URL
PTERO_PANEL_URL = "https://gamep.cloudcrash.shop"

@app.route("/panel")
def panel_proxy():
    try:
        headers = {
            "User-Agent": request.headers.get("User-Agent"),
            "Accept": request.headers.get("Accept", "*/*"),
        }
        resp = requests.get(PTERO_PANEL_URL, headers=headers, timeout=5)

        # Remove X-Frame headers to allow iframe embedding
        content = resp.content
        return Response(content, status=resp.status_code, content_type=resp.headers.get("Content-Type", "text/html"))
    except Exception as e:
        return f"<h1>Error</h1><p>{str(e)}</p>"

@app.route("/")
def viewer():
    return open("index.html").read()

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=10000)
