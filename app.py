from flask import Flask, render_template, request
from mcstatus import JavaServer

app = Flask(__name__)

@app.route("/", methods=['GET','POST'])
def home():
    status = None
    ip = None
    port = None

    if request.method == 'POST':
        ip = request.form.get('ip')
        port = int(request.form.get('port'))

        try:
            server = JavaServer.lookup(f"{ip}:{port}")
            data = server.status()
            status = {
                "online": True,
                "motd": data.description,
                "players": f"{data.players.online}/{data.players.max}",
                "version": data.version.name,
                "ping": data.latency
            }
        except Exception as e:
            status = {
                "online": False,
                "error": str(e)
            }

    return render_template("index.html", status=status, ip=ip, port=port)

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=True)
