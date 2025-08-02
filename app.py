from flask import Flask, render_template, request
import os

app = Flask(__name__)

@app.route("/", methods=["GET", "POST"])
def index():
    url = ""
    if request.method == "POST":
        url = request.form.get("url")
        if not url.startswith("http"):
            url = "https://gamep.cloudcrash.shop/" + url
    return render_template("index.html", url=url)

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8080))
    app.run(host="0.0.0.0", port=port)
