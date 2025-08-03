from flask import Flask, render_template
from mcstatus import MinecraftServer

app = Flask(__name__)

# ===== CONFIG =====
MC_IP = "play.example.com"   # <- change to your server IP
MC_PORT = 25565              # <- change port if needed

@app.route("/")
def home():
    try:
        server = MinecraftServer.lookup(f"{MC_IP}:{MC_PORT}")
        status = server.status()
        
        server_status = {
            "online": True,
            "motd": status.description,
            "players": f"{status.players.online}/{status.players.max}",
            "version": status.version.name,
            "ping": status.latency,
        }
    except Exception as e:
        server_status = {
            "online": False,
            "error": str(e)
        }
        
    return render_template("index.html", status=server_status, ip=MC_IP, port=MC_PORT)

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=True)
