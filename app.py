from flask import Flask, Response, request
import requests

TARGET_URL = "https://gamep.cloudcrash.shop/"

app = Flask(__name__)

@app.route("/")
def fullscreen():
    html = f"""
    <!doctype html>
    <html>
    <head>
        <title>Secure Fullscreen Viewer</title>
        <style>
            html, body {{
                margin: 0;
                padding: 0;
                overflow: hidden;
                height: 100%;
                background: #000;
            }}
            iframe {{
                border: none;
                width: 100vw;
                height: 100vh;
            }}
        </style>
        <script>
            document.oncontextmenu = () => false;
            document.onkeydown = (e) => {{
                if (e.keyCode === 123) return false; // F12
                if (e.ctrlKey && e.shiftKey && (e.keyCode === 73 || e.keyCode === 67)) return false;
            }};
        </script>
    </head>
    <body>
        <iframe src="/proxy" allowfullscreen></iframe>
    </body>
    </html>
    """
    return Response(html, mimetype="text/html")


@app.route("/proxy")
def proxy():
    # Pass-through proxy request to your target site
    r = requests.get(TARGET_URL, params=request.args, headers={
        'User-Agent': request.headers.get('User-Agent', '')
    })
    return Response(r.content, mimetype=r.headers.get("Content-Type", "text/html"))


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=10000)
