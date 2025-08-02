from flask import Flask, render_template, Response, request
import requests

app = Flask(__name__)

# ✅ The site you want to display
TARGET_URL = "https://gamep.cloudcrash.shop"

@app.route("/")
def home():
    return render_template("viewer.html")

@app.route("/proxy")
def proxy():
    try:
        headers = {
            "User-Agent": request.headers.get("User-Agent")
        }
        r = requests.get(TARGET_URL, headers=headers, timeout=5)
        return Response(r.content, content_type=r.headers.get("Content-Type", "text/html"))
    except Exception as e:
        return f"<h1 style='color:red'>Error loading site:</h1><p>{e}</p>"

if __name__ == "__main__":
    import os
    port = int(os.environ.get("PORT", 8080))
    app.run(host="0.0.0.0", port=port)
