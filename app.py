from flask import Flask, request, Response
import requests

app = Flask(__name__)

# Change this to your actual target site
TARGET_URL = "https://gamep.cloudcrash.shop/"

@app.route('/')
def proxy():
    try:
        headers = {
            "User-Agent": request.headers.get("User-Agent"),
            "Accept": "text/html"
        }
        response = requests.get(TARGET_URL, headers=headers, timeout=5)

        return Response(
            response.content,
            status=response.status_code,
            content_type=response.headers.get("Content-Type", "text/html")
        )

    except Exception as e:
        return f"<h1>Error loading site</h1><p>{e}</p>"

if __name__ == '__main__':
    app.run(host="0.0.0.0", port=10000)
