from flask import Flask, Response, render_template_string

HTML_TARGET = "https://gamep.cloudcrash.shop"   # <<< change to your desired URL

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
        document.oncontextmenu = function() {{ return false; }};
        document.onkeydown = function(e) {{
            if (e.keyCode === 123) return false;                    // F12
            if (e.ctrlKey && e.shiftKey && (
                    e.keyCode === 73 || e.keyCode === 67   // Ctrl+Shift+I or Ctrl+Shift+C
                )) return false;
        }};
        </script>
    </head>
    <body>
        <iframe src="{HTML_TARGET}" allowfullscreen></iframe>
    </body>
    </html>
    """
    return Response(html, mimetype="text/html")


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=10000)
