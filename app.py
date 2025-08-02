from flask import Flask, Response, request
import requests

app = Flask(__name__)

# Your Pterodactyl panel URL
TARGET_URL = "https://gamep.cloudcrash.shop"

@app.route("/")
def proxy():
    try:
        # Forward user headers
        headers = {
            "User-Agent": request.headers.get("User-Agent"),
            "Accept": request.headers.get("Accept", "*/*"),
        }

        # Request the original site
        resp = requests.get(TARGET_URL, headers=headers, timeout=5)

        # Relay response content and content type
        return Response(
            resp.content,
            status=resp.status_code,
            content_type=resp.headers.get("Content-Type", "text/html")
        )

    except Exception as e:
        return f"<h1>Failed to load site</h1><p>{str(e)}</p>"

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=10000)
