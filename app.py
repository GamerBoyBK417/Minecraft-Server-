from flask import Flask, jsonify, render_template_string
import requests

app = Flask(__name__)

PANEL_URL = "https://gamep.cloudcrash.shop/"  # Replace with your panel URL
API_KEY = "ptla_1SmcfSTsKbz2eSPGzg08BwlsgXbNF1JeTni2srxL6Zp"     # Replace with your API Key

headers = {
    "Authorization": f"Bearer {API_KEY}",
    "Accept": "Application/vnd.pterodactyl.v1+json",
    "Content-Type": "application/json"
}

@app.route('/')
def dashboard():
    servers = requests.get(f"{PANEL_URL}/api/application/servers", headers=headers).json()
    nodes = requests.get(f"{PANEL_URL}/api/application/nodes", headers=headers).json()
    users = requests.get(f"{PANEL_URL}/api/application/users", headers=headers).json()

    total_servers = len(servers['data'])
    total_users = len(users['data'])
    total_nodes = len(nodes['data'])

    html = f"""
    <!DOCTYPE html>
    <html lang="en">
    <head>
        <meta charset="UTF-8">
        <title>Pterodactyl Public Dashboard</title>
        <script src="https://cdn.tailwindcss.com"></script>
    </head>
    <body class="bg-gray-100 text-gray-800">
        <div class="max-w-4xl mx-auto py-10">
            <h1 class="text-4xl font-bold text-center mb-8">📊 Pterodactyl Public Dashboard</h1>
            <div class="grid grid-cols-1 sm:grid-cols-3 gap-6 text-center">
                <div class="bg-white shadow-md rounded-xl p-6">
                    <p class="text-2xl font-bold">{total_servers}</p>
                    <p>Total Servers</p>
                </div>
                <div class="bg-white shadow-md rounded-xl p-6">
                    <p class="text-2xl font-bold">{total_users}</p>
                    <p>Total Users</p>
                </div>
                <div class="bg-white shadow-md rounded-xl p-6">
                    <p class="text-2xl font-bold">{total_nodes}</p>
                    <p>Total Nodes</p>
                </div>
            </div>
        </div>
    </body>
    </html>
    """
    return render_template_string(html)

if __name__ == '__main__':
    app.run()
