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
        res = requests.get(TARGET_URL, headers={"User-Agent": request.headers.get("User-Agent")})
        html = res.text

        # Parse HTML and rewrite all asset URLs
        soup = BeautifulSoup(html, "html.parser")

        # Rewriting logic
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
                    url = urllib.parse.urljoin(TARGET_URL, url)
                    proxied_url = "/fetch?url=" + urllib.parse.quote(url)
                    element[attr] = proxied_url

        return Response(str(soup), content_type="text/html")

    except Exception as e:
        return f"<h1>Error loading site: {e}</h1>", 500

@app.route("/fetch")
def fetch_resource():
    url = request.args.get("url")
    try:
        r = requests.get(url, headers={"User-Agent": request.headers.get("User-Agent")})
        return Response(r.content, content_type=r.headers.get("Content-Type"))
    except Exception as e:
        return f"Error loading resource: {e}", 500

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=8080)
