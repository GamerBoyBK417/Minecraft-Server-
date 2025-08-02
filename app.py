from flask import Flask, render_template_string, request, redirect
import requests
import os

app = Flask(__name__)

PANEL_URL = os.getenv("PANEL_URL", "https://gamep.cloudcrash.shop")
API_KEY = os.getenv("API_KEY", "ptla_1SmcfSTsKbz2eSPGzg08BwlsgXbNF1JeTni2srxL6Zp")

headers = {
    "Authorization": f"Bearer {API_KEY}",
    "Accept": "Application/vnd.pterodactyl.v1+json",
    "Content-Type": "application/json"
}

@app.route('/')
def dashboard():
    try:
        servers = requests.get(f"{PANEL_URL}/api/application/servers", headers=headers).json()
        nodes = requests.get(f"{PANEL_URL}/api/application/nodes", headers=headers).json()
        users = requests.get(f"{PANEL_URL}/api/application/users", headers=headers).json()

        total_servers = len(servers['data'])
        total_users = len(users['data'])
        total_nodes = len(nodes['data'])

        server_cards = ""
        for server in servers['data']:
            name = server['attributes']['name']
            uuid = server['attributes']['uuid']
            identifier = server['attributes']['identifier']
            suspended = server['attributes']['suspended']
            suspend_button = (
                f"""
                <form method="POST" action="/control/{uuid}/unsuspend" class="inline">
                    <button class="bg-green-500 hover:bg-green-600 text-white px-3 py-1 rounded">Unsuspend</button>
                </form>
                """ if suspended else
                f"""
                <form method="POST" action="/control/{uuid}/suspend" class="inline">
                    <button class="bg-red-500 hover:bg-red-600 text-white px-3 py-1 rounded">Suspend</button>
                </form>
                """
            )

            server_cards += f"""
            <div class="bg-white shadow-md rounded-xl p-6">
                <p class="font-bold">{name}</p>
                <p class="text-sm text-gray-500 mb-2">UUID: {identifier}</p>
                {suspend_button}
            </div>
            """

        html = f"""
        <!DOCTYPE html>
        <html lang="en">
        <head>
            <meta charset="UTF-8">
            <title>Pterodactyl Control Dashboard</title>
            <script src="https://cdn.tailwindcss.com"></script>
        </head>
        <body class="bg-gray-100 text-gray-800">
            <div class="max-w-6xl mx-auto py-10 px-4">
                <h1 class="text-4xl font-bold text-center mb-8">🛠️ Pterodactyl Control Panel</h1>
                <div class="grid grid-cols-1 sm:grid-cols-3 gap-6 text-center mb-10">
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

                <h2 class="text-2xl font-semibold mb-4">Server Controls</h2>
                <div class="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-6">
                    {server_cards}
                </div>
            </div>
        </body>
        </html>
        """
        return render_template_string(html)

    except Exception as e:
        return f"<h1>Error loading data: {e}</h1>", 500

@app.route('/control/<uuid>/<action>', methods=["POST"])
def control_server(uuid, action):
    if action == "suspend":
        url = f"{PANEL_URL}/api/application/servers/{uuid}/suspend"
    elif action == "unsuspend":
        url = f"{PANEL_URL}/api/application/servers/{uuid}/unsuspend"
    else:
        return "Invalid action", 400

    response = requests.post(url, headers=headers)
    return redirect('/')

if __name__ == '__main__':
    app.run(host="0.0.0.0", port=8080)
