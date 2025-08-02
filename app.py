from flask import Flask, Response, render_template, request
import requests
from bs4 import BeautifulSoup
import urllib.parse

app = Flask(__name__)
TARGET_URL = "https://gamep.cloudcrash.shop"

@app.route("/")
def index():
    return render_template("viewer.html")

@app.route("/proxy")
def proxy():
    try:
        headers = {
            "User-Agent": request.headers.get("User-Agent", "Mozilla/5.0")
        }
        res = requests.get(TARGET_URL, headers=headers, timeout=10)
        html = res.text

        soup = BeautifulSoup(html, "html.parser")

        tags = {
            "link": "href",
            "script": "src",
            "img": "src",
            "iframe": "src",
            "a": "href"
        }

        for tag, attr in tags.items():
            for element in soup.find_all(tag):
                url = element.get(attr)
                if url and not url.startswith("http"):
                    full_url = urllib.parse.urljoin(TARGET_URL, url)
                    proxied_url = "/fetch?url=" + urllib.parse.quote(full_url)
                    element[attr] = proxied_url

        return Response(str(soup), content_type="text/html")

    except Exception as e:
        return f"<h1>Proxy error: {e}</h1>"

@app.route("/fetch")
def fetch():
    url = request.args.get("url")
    try:
        r = requests.get(url, headers={"User-Agent": request.headers.get("User-Agent", "Mozilla/5.0")})
        return Response(r.content, content_type=r.headers.get("Content-Type"))
    except Exception as e:
        return f"Fetch error: {e}", 500

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=8080)
