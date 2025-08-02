from flask import Flask, render_template, Response, request
import requests

app = Flask(__name__)

TARGET_SITE = "https://gamep.cloudcrash.shop"  # Your real site

@app.route("/")
def viewer():
    return render_template("viewer.html")

@app.route("/proxy")
def proxy():
    try:
        r = requests.get(TARGET_SITE, headers={
            "User-Agent": request.headers.get("User-Agent")
        })
        return Response(r.content, content_type=r.headers.get("Content-Type"))
    except Exception as e:
        return f"Error loading site: {str(e)}", 500

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=8080)
