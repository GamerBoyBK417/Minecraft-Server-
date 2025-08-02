from flask import Flask, render_template
import urllib.parse

app = Flask(__name__)

@app.route("/")
def screenshot_viewer():
    target_url = "https://gamep.cloudcrash.shop"

    # Encode target URL
    encoded_url = urllib.parse.quote(target_url, safe='')

    # Screenshot API (Free for light usage)
    image_url = f"https://image.thum.io/get/fullpage/{encoded_url}"

    return render_template("viewer.html", image_url=image_url)

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=8080)
