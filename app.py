from flask import Flask, render_template_string, request, redirect, flash, session, jsonify
from dotenv import load_dotenv
import requests
import os
import logging
from datetime import datetime
import secrets
import re
import time
from functools import wraps

# Load environment variables from .env file
load_dotenv()

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

app = Flask(__name__)
app.secret_key = os.getenv("SECRET_KEY")

# --- Configuration ---
PANEL_URL = os.getenv("PANEL_URL")
API_KEY = os.getenv("API_KEY")
ADMIN_USERNAME = os.getenv("ADMIN_USERNAME")
ADMIN_PASSWORD = os.getenv("ADMIN_PASSWORD")

if not all([PANEL_URL, API_KEY, ADMIN_USERNAME, ADMIN_PASSWORD, app.secret_key]):
    logger.error("One or more environment variables are missing! Please check your .env file.")
    exit(1)

headers = {
    "Authorization": f"Bearer {API_KEY}",
    "Accept": "Application/vnd.pterodactyl.v1+json",
    "Content-Type": "application/json"
}

# --- Rate limiting ---
request_times = {}
RATE_LIMIT = 60  # requests per minute

def rate_limit(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        client_ip = request.remote_addr
        current_time = time.time()
        if client_ip not in request_times:
            request_times[client_ip] = []
        request_times[client_ip] = [t for t in request_times[client_ip] if current_time - t < 60]
        if len(request_times[client_ip]) >= RATE_LIMIT:
            return jsonify({"error": "Rate limit exceeded"}), 429
        request_times[client_ip].append(current_time)
        return f(*args, **kwargs)
    return decorated_function

# --- Authentication & Authorization ---
def login_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not session.get('logged_in'):
            return redirect('/login')
        return f(*args, **kwargs)
    return decorated_function

def verify_csrf(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        token = session.get('_csrf_token')
        if not token or token != request.form.get('_csrf_token'):
            flash('Invalid or missing CSRF token.', 'error')
            return redirect('/')
        return f(*args, **kwargs)
    return decorated_function

# --- Utility Functions ---
def validate_uuid(uuid_string):
    uuid_pattern = re.compile(r'^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$', re.IGNORECASE)
    return bool(uuid_pattern.match(str(uuid_string)))

def make_api_request(endpoint, method='GET', data=None, params=None, paginated=False):
    url = f"{PANEL_URL}/api/application/{endpoint}"
    try:
        if method == 'GET' and paginated:
            all_data = []
            page_url = url
            while page_url:
                response = requests.get(page_url, headers=headers, timeout=10, params=params)
                response.raise_for_status()
                json_response = response.json()
                all_data.extend(json_response.get('data', []))
                page_url = json_response.get('meta', {}).get('pagination', {}).get('links', {}).get('next')
                params = None
            return {"data": all_data}, None

        response = requests.request(method, url, headers=headers, json=data, params=params, timeout=10)
        
        if response.status_code == 429:
            logger.warning("API rate limit hit")
            return None, "API rate limit exceeded. Please wait a moment."
        
        response.raise_for_status()
        return response.json() if response.content else {}, None
        
    except requests.exceptions.Timeout:
        logger.error(f"API request timeout: {endpoint}")
        return None, "The request to the panel API timed out."
    except requests.exceptions.RequestException as e:
        logger.error(f"API request failed: {endpoint} - {e}")
        return None, "An error occurred while communicating with the Pterodactyl panel."

# --- Templates ---
LOGIN_TEMPLATE = """
<!DOCTYPE html><html lang="en"><head><meta charset="UTF-8"><meta name="viewport" content="width=device-width, initial-scale=1.0"><title>Login - Pterodactyl Dashboard</title><script src="https://cdn.tailwindcss.com"></script></head><body class="bg-gradient-to-br from-blue-900 via-purple-900 to-indigo-900 min-h-screen flex items-center justify-center"><div class="bg-white/10 backdrop-blur-lg rounded-2xl p-8 w-full max-w-md shadow-2xl"><h1 class="text-3xl font-bold text-white text-center mb-8">🛠️ Pterodactyl Dashboard</h1>{% with messages = get_flashed_messages(with_categories=true) %}{% if messages %}{% for category, message in messages %}<div class="mb-4 p-3 rounded-lg {{ 'bg-red-500/20 text-red-200' if category == 'error' else 'bg-green-500/20 text-green-200' }}">{{ message }}</div>{% endfor %}{% endif %}{% endwith %}<form method="POST" class="space-y-6"><div><label class="block text-white mb-2">Username</label><input type="text" name="username" required class="w-full p-3 rounded-lg bg-white/20 text-white placeholder-white/60 border border-white/30 focus:border-white/60 focus:outline-none"></div><div><label class="block text-white mb-2">Password</label><input type="password" name="password" required class="w-full p-3 rounded-lg bg-white/20 text-white placeholder-white/60 border border-white/30 focus:border-white/60 focus:outline-none"></div><button type="submit" class="w-full bg-blue-600 hover:bg-blue-700 text-white font-bold py-3 px-4 rounded-lg transition-colors">Login</button></form></div></body></html>
"""
DASHBOARD_TEMPLATE = """
<!DOCTYPE html><html lang="en"><head><meta charset="UTF-8"><meta name="viewport" content="width=device-width, initial-scale=1.0"><title>Pterodactyl Control Dashboard</title><script src="https://cdn.tailwindcss.com"></script><style>.stat-card{background:linear-gradient(135deg,rgba(255,255,255,0.1),rgba(255,255,255,0.05));backdrop-filter:blur(10px);border:1px solid rgba(255,255,255,0.2)}</style></head><body class="bg-gradient-to-br from-blue-900 via-purple-900 to-indigo-900 min-h-screen text-white"><nav class="bg-black/20 backdrop-blur-lg border-b border-white/10 sticky top-0 z-10"><div class="max-w-7xl mx-auto px-4 py-4"><div class="flex justify-between items-center"><h1 class="text-2xl font-bold">🛠️ Pterodactyl Dashboard</h1><div class="flex items-center gap-4"><span class="text-sm text-gray-300">Welcome, {{ session.username }}</span><a href="/logout" class="bg-red-500 hover:bg-red-600 px-4 py-2 rounded-lg text-sm transition-colors">Logout</a></div></div></div></nav><main class="max-w-7xl mx-auto py-8 px-4">{% with messages=get_flashed_messages(with_categories=true) %}{% if messages %}{% for category,message in messages %}<div class="mb-6 p-4 rounded-lg {{'bg-red-500/20 border border-red-500/50 text-red-200' if category=='error' else 'bg-green-500/20 border border-green-500/50 text-green-200'}}">{{ message }}</div>{% endfor %}{% endif %}{% endwith %}<div class="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-6 mb-8"><div class="stat-card rounded-xl p-6 text-center"><div class="text-3xl font-bold text-blue-400">{{ stats.total_servers }}</div><div class="text-gray-300">Total Servers</div></div><div class="stat-card rounded-xl p-6 text-center"><div class="text-3xl font-bold text-green-400">{{ stats.online_servers }}</div><div class="text-gray-300">Online Servers</div></div><div class="stat-card rounded-xl p-6 text-center"><div class="text-3xl font-bold text-red-400">{{ stats.suspended_servers }}</div><div class="text-gray-300">Suspended</div></div><div class="stat-card rounded-xl p-6 text-center"><div class="text-3xl font-bold text-purple-400">{{ stats.total_users }}</div><div class="text-gray-300">Total Users</div></div></div><div class="mb-6"><div class="border-b border-white/20"><nav class="-mb-px flex space-x-8"><button onclick="showTab('servers')" id="servers-tab" class="tab-button border-b-2 border-blue-500 text-blue-400 py-2 px-1 font-medium text-sm">Servers</button><button onclick="showTab('nodes')" id="nodes-tab" class="tab-button border-b-2 border-transparent text-gray-400 hover:text-gray-300 py-2 px-1 font-medium text-sm">Nodes</button></nav></div></div><div id="servers-content" class="tab-content"><div class="flex justify-between items-center mb-6"><h2 class="text-2xl font-semibold">Server Management</h2><a href="/" class="bg-blue-500 hover:bg-blue-600 px-4 py-2 rounded-lg transition-colors">🔄 Refresh</a></div><div class="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6">{% for server in servers %}<div class="bg-white/10 backdrop-blur-lg rounded-xl p-6 border border-white/20 hover:border-white/40 transition-all"><div class="flex justify-between items-start mb-3"><h3 class="font-bold text-white text-lg truncate" title="{{ server.attributes.name }}">{{ server.attributes.name }}</h3>{% if server.attributes.suspended %}<span class="px-2 py-1 rounded-full text-xs font-semibold bg-red-100 text-red-800">Suspended</span>{% else %}<span class="px-2 py-1 rounded-full text-xs font-semibold bg-green-100 text-green-800">Online</span>{% endif %}</div><div class="text-gray-300 text-sm space-y-1 mb-4"><p><span class="font-medium">ID:</span> {{ server.attributes.identifier }}</p><p><span class="font-medium">UUID:</span> <span class="font-mono">{{ server.attributes.uuid[:8] }}...</span></p></div><div class="flex gap-2">{% if server.attributes.suspended %}<form method="POST" action="/control/{{ server.attributes.uuid }}/unsuspend" class="inline" onsubmit="return confirm('Unsuspend this server?')"><input type="hidden" name="_csrf_token" value="{{ session._csrf_token }}"><button class="bg-green-500 hover:bg-green-600 text-white px-3 py-1 rounded-lg text-sm transition-colors">Unsuspend</button></form>{% else %}<form method="POST" action="/control/{{ server.attributes.uuid }}/suspend" class="inline" onsubmit="return confirm('Suspend this server?')"><input type="hidden" name="_csrf_token" value="{{ session._csrf_token }}"><button class="bg-red-500 hover:bg-red-600 text-white px-3 py-1 rounded-lg text-sm transition-colors">Suspend</button></form>{% endif %}<button onclick="viewServerDetails('{{ server.attributes.uuid }}')" class="bg-blue-500 hover:bg-blue-600 text-white px-3 py-1 rounded-lg text-sm transition-colors">Details</button></div></div>{% else %}<p class="text-gray-400 md:col-span-2 lg:col-span-3">No servers found or failed to load servers.</p>{% endfor %}</div></div><div id="nodes-content" class="tab-content hidden"><h2 class="text-2xl font-semibold mb-6">Node Information</h2><div class="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6">{% for node in nodes %}<div class="bg-white/10 backdrop-blur-lg rounded-xl p-6 border border-white/20"><h3 class="font-bold text-white text-lg mb-2">{{ node.attributes.name }}</h3><div class="text-gray-300 text-sm space-y-1"><p><span class="font-medium">Location ID:</span> {{ node.attributes.location_id }}</p><p><span class="font-medium">Memory:</span> {{ node.attributes.memory }} MB</p><p><span class="font-medium">Disk:</span> {{ node.attributes.disk }} MB</p></div></div>{% else %}<p class="text-gray-400 md:col-span-2 lg:col-span-3">No nodes found or failed to load nodes.</p>{% endfor %}</div></div></main><div id="serverModal" class="fixed inset-0 bg-black/50 backdrop-blur-sm hidden items-center justify-center z-50 p-4"><div class="bg-white/10 backdrop-blur-lg rounded-2xl p-6 w-full max-w-2xl mx-4 border border-white/20"><div class="flex justify-between items-center mb-4"><h3 class="text-xl font-bold">Server Details</h3><button onclick="closeModal()" class="text-gray-400 hover:text-white text-2xl">&times;</button></div><div id="serverDetails" class="text-gray-300 max-h-[70vh] overflow-y-auto">Loading...</div></div></div><script>function showTab(t){document.querySelectorAll(".tab-content").forEach(e=>e.classList.add("hidden")),document.querySelectorAll(".tab-button").forEach(e=>{e.classList.remove("border-blue-500","text-blue-400"),e.classList.add("border-transparent","text-gray-400")}),document.getElementById(t+"-content").classList.remove("hidden");let e=document.getElementById(t+"-tab");e.classList.remove("border-transparent","text-gray-400"),e.classList.add("border-blue-500","text-blue-400")}function closeModal(){document.getElementById("serverModal").classList.add("hidden")}function viewServerDetails(t){let e=document.getElementById("serverModal");e.classList.remove("hidden"),document.getElementById("serverDetails").innerHTML="Loading...",fetch(`/api/server/${t}`).then(t=>t.json()).then(t=>{document.getElementById("serverDetails").innerHTML=t.error?`<p class="text-red-400">Error: ${t.error}</p>`:`<div class="space-y-3 font-mono text-sm"><div><strong>Name:</strong> ${t.name}</div><div><strong>UUID:</strong> ${t.uuid}</div><div><strong>Identifier:</strong> ${t.identifier}</div><div><strong>Status:</strong> <span class="${t.suspended?"text-red-400":"text-green-400"}">${t.suspended?"Suspended":"Active"}</span></div><div><strong>Node:</strong> ${t.node}</div><div><strong>Created:</strong> ${new Date(t.created_at).toLocaleString()}</div><div><strong>Updated:</strong> ${new Date(t.updated_at).toLocaleString()}</div></div>`}).catch(t=>{console.error(t),document.getElementById("serverDetails").innerHTML='<p class="text-red-400">Error loading server details.</p>'})}document.getElementById("serverModal").addEventListener("click",function(t){"serverModal"===t.target.id&&closeModal()});</script></body></html>
"""

# --- Routes ---
@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form.get('username', '').strip()
        password = request.form.get('password', '').strip()
        
        if username == ADMIN_USERNAME and password == ADMIN_PASSWORD:
            session['logged_in'] = True
            session['username'] = username
            session['_csrf_token'] = secrets.token_hex(16)
            logger.info(f"Successful login for '{username}' from {request.remote_addr}")
            return redirect('/')
        else:
            logger.warning(f"Failed login attempt from {request.remote_addr}")
            flash('Invalid credentials!', 'error')
    return render_template_string(LOGIN_TEMPLATE)

@app.route('/logout')
def logout():
    session.clear()
    flash('Successfully logged out!', 'success')
    return redirect('/login')

@app.route('/')
@login_required
@rate_limit
def dashboard():
    servers_data, s_err = make_api_request("servers", paginated=True)
    nodes_data, n_err = make_api_request("nodes", paginated=True)
    users_data, u_err = make_api_request("users", paginated=True)
    
    if s_err or n_err or u_err:
        flash(f"Could not load all panel data. Errors: {s_err or ''} {n_err or ''} {u_err or ''}".strip(), 'error')

    servers = servers_data.get('data', []) if servers_data else []
    nodes = nodes_data.get('data', []) if nodes_data else []
    users_count = len(users_data.get('data', [])) if users_data else 0

    stats = {
        'total_servers': len(servers),
        'suspended_servers': sum(1 for s in servers if s.get('attributes', {}).get('suspended')),
        'total_users': users_count,
        'total_nodes': len(nodes)
    }
    stats['online_servers'] = stats['total_servers'] - stats['suspended_servers']
    
    return render_template_string(DASHBOARD_TEMPLATE, stats=stats, servers=servers, nodes=nodes)

@app.route('/api/server/<uuid>')
@login_required
@rate_limit
def get_server_details(uuid):
    if not validate_uuid(uuid):
        return jsonify({"error": "Invalid UUID format"}), 400
    server_data, error = make_api_request(f"servers/{uuid}")
    if error:
        return jsonify({"error": error}), 500
    if isinstance(server_data, dict) and 'attributes' in server_data:
        return jsonify(server_data['attributes'])
    else:
        logger.warning(f"Unexpected API response for server {uuid}: {server_data}")
        return jsonify({"error": "Failed to retrieve valid server details."}), 500

@app.route('/control/<uuid>/<action>', methods=["POST"])
@login_required
@rate_limit
@verify_csrf
def control_server(uuid, action):
    if not validate_uuid(uuid):
        flash("Invalid server UUID format.", 'error')
        return redirect('/')
    if action not in ['suspend', 'unsuspend']:
        flash("Invalid action specified.", 'error')
        return redirect('/')
    
    _, error = make_api_request(f"servers/{uuid}/{action}", 'POST')
    if error:
        flash(f"Failed to {action} server: {error}", 'error')
    else:
        flash(f"Server successfully {'suspended' if action == 'suspend' else 'unsuspended'}.", 'success')
    return redirect('/')

# --- Error Handlers ---
@app.errorhandler(404)
def not_found(error):
    return "<h1>404 Not Found</h1><p>The page you are looking for does not exist.</p><a href='/'>Go Home</a>", 404

@app.errorhandler(500)
def server_error(error):
    logger.error(f"Server Error: {error}")
    return "<h1>500 Internal Server Error</h1><p>Something went wrong on our end.</p><a href='/'>Go Home</a>", 500

if __name__ == '__main__':
    print("🚀 Starting Pterodactyl Control Dashboard...")
    print(f"📊 Panel URL: {PANEL_URL}")
    app.run(host="0.0.0.0", port=8080, debug=False)
