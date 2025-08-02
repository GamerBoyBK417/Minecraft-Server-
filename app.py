from flask import Flask, render_template_string, request, redirect, flash, session, jsonify
from dotenv import load_dotenv
import requests
import os
import logging
import secrets
import re
import time
from functools import wraps
from urllib.parse import urlparse

# --- Initial Setup ---
load_dotenv()
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

app = Flask(__name__)

# --- Configuration & Validation ---
class Config:
    PANEL_URL = os.getenv("PANEL_URL", "").rstrip('/')
    API_KEY = os.getenv("API_KEY")
    ADMIN_USERNAME = os.getenv("ADMIN_USERNAME")
    ADMIN_PASSWORD = os.getenv("ADMIN_PASSWORD")
    SECRET_KEY = os.getenv("SECRET_KEY", secrets.token_hex(32)) # Feature 1: Dynamic Secret Key

    @classmethod
    def validate(cls):
        missing_vars = []
        if not cls.PANEL_URL: missing_vars.append("PANEL_URL")
        if not cls.API_KEY: missing_vars.append("API_KEY")
        if not cls.ADMIN_USERNAME: missing_vars.append("ADMIN_USERNAME")
        if not cls.ADMIN_PASSWORD: missing_vars.append("ADMIN_PASSWORD")

        if missing_vars:
            logger.error(f"FATAL: Missing critical environment variables: {', '.join(missing_vars)}")
            exit(1)
        
        if not urlparse(cls.PANEL_URL).scheme in ['http', 'https']:
            logger.error("FATAL: PANEL_URL appears to be invalid. Please include http:// or https://")
            exit(1)
            
        if not os.getenv("SECRET_KEY"):
            logger.warning("SECRET_KEY not set in .env, using a temporary secret key. Sessions will not persist across restarts.")

app.config.from_object(Config)
Config.validate()

# --- Pterodactyl API Client ---
class PterodactylAPI:
    def __init__(self, panel_url, api_key):
        self.base_url = f"{panel_url}/api/application"
        self.headers = {
            "Authorization": f"Bearer {api_key}",
            "Accept": "Application/vnd.pterodactyl.v1+json",
            "Content-Type": "application/json"
        }

    def _request(self, endpoint, method='GET', data=None, params=None):
        url = f"{self.base_url}/{endpoint}"
        try:
            response = requests.request(method, url, headers=self.headers, json=data, params=params, timeout=15)
            
            if response.status_code == 429:
                return None, "API rate limit hit. Please try again in a moment."

            response.raise_for_status()
            return response.json() if response.content else {}, None
        
        except requests.exceptions.Timeout as e:
            logger.error(f"API Timeout: {method} {url} - {e}")
            return None, "Request to the panel API timed out."
        except requests.exceptions.HTTPError as e:
            logger.error(f"API HTTP Error: {method} {url} - {e.response.status_code} {e.response.text}")
            error_msg = f"API request failed with status {e.response.status_code}."
            try: # Try to get specific pterodactyl error
                errors = e.response.json().get('errors', [])
                if errors:
                    error_msg = errors[0]['detail']
            except:
                pass
            return None, error_msg
        except requests.exceptions.RequestException as e:
            logger.error(f"API Request Failed: {method} {url} - {e}")
            return None, "A critical error occurred while communicating with the Pterodactyl panel."
    
    def get_paged_data(self, endpoint, params=None):
        if params is None:
            params = {}
        return self._request(endpoint, 'GET', params=params)

    def get_all_data(self, endpoint):
        all_data = []
        url = f"{self.base_url}/{endpoint}"
        params = {'per_page': 100} # Fetch 100 at a time
        
        while url:
            try:
                response = requests.get(url, headers=self.headers, params=params, timeout=15)
                response.raise_for_status()
                json_data = response.json()
                all_data.extend(json_data['data'])
                url = json_data.get('meta', {}).get('pagination', {}).get('links', {}).get('next')
                params = None # The 'next' URL already contains all necessary params
            except requests.exceptions.RequestException as e:
                logger.error(f"Failed to fetch all data from {endpoint}: {e}")
                return None, f"Could not fetch all data from {endpoint}."
        
        return {'data': all_data}, None

    def get_server_details(self, uuid):
        return self._request(f"servers/{uuid}")

    def control_server(self, uuid, action, data=None):
        endpoint = f"servers/{uuid}/{action}"
        return self._request(endpoint, 'POST', data=data)

api_client = PterodactylAPI(app.config['PANEL_URL'], app.config['API_KEY'])

# --- Middleware & Decorators ---
request_times = {}
def rate_limit(limit=30, per=60): # 30 requests per 60 seconds
    def decorator(f):
        @wraps(f)
        def wrapped(*args, **kwargs):
            client_ip = request.remote_addr
            current_time = time.time()
            if client_ip not in request_times:
                request_times[client_ip] = []
            
            # Clear old timestamps
            request_times[client_ip] = [t for t in request_times[client_ip] if current_time - t < per]
            
            if len(request_times[client_ip]) >= limit:
                return jsonify({"error": "Rate limit exceeded"}), 429
            
            request_times[client_ip].append(current_time)
            return f(*args, **kwargs)
        return wrapped
    return decorator

def login_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not session.get('logged_in'):
            return redirect('/login')
        if '_csrf_token' not in session: # Ensure CSRF token exists
            session['_csrf_token'] = secrets.token_hex(16)
        return f(*args, **kwargs)
    return decorated_function

@app.after_request
def add_security_headers(response): # Feature 11: Security Headers
    response.headers['X-Content-Type-Options'] = 'nosniff'
    response.headers['X-Frame-Options'] = 'SAMEORIGIN'
    response.headers['X-XSS-Protection'] = '1; mode=block'
    # A strict CSP can break inline scripts/styles. The current template uses them.
    # For a real production app, move all JS/CSS to static files and enable a stricter policy.
    # response.headers['Content-Security-Policy'] = "default-src 'self'; script-src 'self'; style-src 'self' https://cdn.tailwindcss.com; object-src 'none';"
    return response

# --- Utility Functions ---
def validate_uuid(uuid_string):
    uuid_pattern = re.compile(r'^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$', re.IGNORECASE)
    return bool(uuid_pattern.match(str(uuid_string)))

# --- Templates (Minified for brevity) ---
LOGIN_TEMPLATE = """
<!DOCTYPE html><html lang="en"><head><meta charset="UTF-8"><meta name="viewport" content="width=device-width, initial-scale=1.0"><title>Login</title><script src="https://cdn.tailwindcss.com"></script></head><body class="bg-gray-900 flex items-center justify-center min-h-screen"><div class="bg-gray-800 p-8 rounded-lg shadow-xl w-full max-w-sm"><h1 class="text-2xl font-bold text-white text-center mb-6">Admin Dashboard</h1>{% with messages = get_flashed_messages(with_categories=true) %}{% if messages %}<div class="mb-4 p-3 rounded-md bg-red-500/20 text-red-300">{{ messages[0][1] }}</div>{% endif %}{% endwith %}<form method="POST" class="space-y-4"><input type="text" name="username" placeholder="Username" required class="w-full p-3 bg-gray-700 text-white rounded-md border border-gray-600 focus:outline-none focus:ring-2 focus:ring-blue-500"><input type="password" name="password" placeholder="Password" required class="w-full p-3 bg-gray-700 text-white rounded-md border border-gray-600 focus:outline-none focus:ring-2 focus:ring-blue-500"><button type="submit" class="w-full bg-blue-600 hover:bg-blue-700 text-white font-bold py-3 rounded-md transition-colors">Login</button></form></div></body></html>
"""
DASHBOARD_TEMPLATE = """
<!DOCTYPE html><html lang="en"><head><meta charset="UTF-8"><meta name="viewport" content="width=device-width, initial-scale=1.0"><title>Pterodactyl Dashboard</title><script src="https://cdn.tailwindcss.com"></script><style>body{background-color:#0d1117;color:#c9d1d9}nav{background-color:#161b22;border-bottom:1px solid #30363d}.stat-card,.content-card{background-color:rgba(22,27,34,0.6);border:1px solid #30363d;backdrop-filter:blur(12px)}.tab-button.active{border-color:#58a6ff;color:#58a6ff}.toast{position:fixed;bottom:20px;right:20px;padding:12px 20px;border-radius:8px;z-index:1000;color:white;opacity:0;transform:translateY(20px);transition:opacity .3s, transform .3s}.toast.show{opacity:1;transform:translateY(0)}.toast.success{background-color:#238636}.toast.error{background-color:#da3633}.loader{border:4px solid #30363d;border-top:4px solid #58a6ff;border-radius:50%;width:32px;height:32px;animation:spin 1s linear infinite}@keyframes spin{0%{transform:rotate(0deg)}100%{transform:rotate(360deg)}}.copy-btn{cursor:pointer;opacity:0.6;transition:opacity .2s}.copy-btn:hover{opacity:1}</style></head><body><div id="toast-container"></div><nav class="sticky top-0 z-50"><div class="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8"><div class="flex items-center justify-between h-16"><div class="flex items-center"><span class="font-bold text-xl text-white">Admin Panel</span><div id="api-status" class="ml-4 flex items-center gap-2 text-xs"><div class="h-2 w-2 rounded-full bg-yellow-500 animate-pulse"></div><span>Checking...</span></div></div><div class="flex items-center gap-4"><span class="text-sm text-gray-400">Welcome, {{ session.username }}</span><a href="/logout" class="bg-red-600 hover:bg-red-700 text-white px-3 py-1.5 rounded-md text-sm font-medium">Logout</a></div></div></div></nav><main class="max-w-7xl mx-auto py-6 sm:px-6 lg:px-8"><div class="grid grid-cols-2 lg:grid-cols-4 gap-4 mb-6">{% for key, value in stats.items() %}<div class="stat-card p-4 rounded-lg text-center"><p class="text-3xl font-bold">{{ value }}</p><p class="text-sm text-gray-400 capitalize">{{ key.replace('_', ' ') }}</p></div>{% endfor %}</div><div class="content-card rounded-lg p-6"><div class="border-b border-gray-700 mb-4"><div class="flex space-x-4"><button id="servers-tab" onclick="showTab('servers')" class="tab-button active py-2 px-1 text-sm font-medium border-b-2">Servers</button><button id="users-tab" onclick="showTab('users')" class="tab-button py-2 px-1 text-sm font-medium border-b-2 border-transparent text-gray-400 hover:text-white">Users</button><button id="nodes-tab" onclick="showTab('nodes')" class="tab-button py-2 px-1 text-sm font-medium border-b-2 border-transparent text-gray-400 hover:text-white">Nodes</button></div></div><div id="servers-content" class="tab-content"><div class="flex flex-col md:flex-row gap-4 justify-between items-center mb-4"><h2 class="text-xl font-semibold">Server Management</h2><div class="flex gap-2 w-full md:w-auto"><form id="search-form" class="flex-grow flex gap-2"><input type="search" name="q" placeholder="Search by name..." value="{{ request.args.get('q', '') }}" class="w-full md:w-64 p-2 bg-gray-900 border border-gray-700 rounded-md text-sm"><select name="suspended" class="p-2 bg-gray-900 border border-gray-700 rounded-md text-sm"><option value="">All Statuses</option><option value="true" {% if request.args.get('suspended') == 'true' %}selected{% endif %}>Suspended</option><option value="false" {% if request.args.get('suspended') == 'false' %}selected{% endif %}>Active</option></select><button type="submit" class="bg-blue-600 hover:bg-blue-700 text-white px-4 py-2 rounded-md text-sm">Filter</button></form></div></div><div id="server-list" class="space-y-4"></div><div id="servers-loader" class="flex justify-center p-8"><div class="loader"></div></div><div id="server-pagination" class="flex justify-between items-center mt-4 text-sm"></div></div><div id="users-content" class="tab-content hidden"><h2 class="text-xl font-semibold mb-4">User List</h2><div id="user-list" class="space-y-2"></div><div id="users-loader" class="flex justify-center p-8"><div class="loader"></div></div></div><div id="nodes-content" class="tab-content hidden"><h2 class="text-xl font-semibold mb-4">Node Status</h2><div id="node-list" class="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4"></div><div id="nodes-loader" class="flex justify-center p-8"><div class="loader"></div></div></div></div></main><script>const csrf_token="{{session._csrf_token}}";function showTab(t){document.querySelectorAll(".tab-content").forEach(e=>e.classList.add("hidden")),document.querySelectorAll(".tab-button").forEach(e=>e.classList.remove("active","border-blue-500","text-blue-500")),document.getElementById(t+"-content").classList.remove("hidden"),document.getElementById(t+"-tab").classList.add("active","border-blue-500","text-blue-500")}function showToast(t,e="success"){const o=document.getElementById("toast-container"),n=document.createElement("div");n.textContent=t,n.className=`toast ${e}`,o.appendChild(n),setTimeout(()=>n.classList.add("show"),10),setTimeout(()=>{n.classList.remove("show"),setTimeout(()=>o.removeChild(n),300)},3e3)}function copyToClipboard(t,e){navigator.clipboard.writeText(t).then(()=>showToast(`Copied ${e}!`)).catch(()=>showToast("Failed to copy.","error"))}async function apiAction(t,e,o){try{const n={method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify({_csrf_token:csrf_token})};let s=await fetch(`/control/${t}/${e}`,n);if(!s.ok)throw new Error(await s.text());const a=await s.json();showToast(a.message,"success"),"servers"==o&&loadServers(new URLSearchParams(window.location.search).get("page")||1)}catch(t){console.error("API Action Error:",t);let e=t.message;try{e=JSON.parse(t.message).error||e}catch(o){}showToast(`Error: ${e}`,"error")}}function confirmAndAct(t,e,o){if(confirm(`Are you sure you want to ${o} this server?`))return apiAction(t,e,"servers")}const renderServers=(t,e)=>{const o=document.getElementById("server-list");o.innerHTML="",t.forEach(t=>{const n=t.attributes,i=n.suspended;o.innerHTML+=`<div class="content-card p-4 rounded-lg flex flex-col md:flex-row justify-between items-center gap-4"><div class="flex-grow"><div class="flex items-center gap-2"><h3 class="font-bold text-lg text-white">${n.name}</h3><span class="px-2 py-0.5 rounded-full text-xs font-semibold ${i?"bg-red-900 text-red-300":"bg-green-900 text-green-300"}">${i?"Suspended":"Active"}</span></div><div class="text-gray-400 text-xs font-mono mt-1"><span>ID: ${n.identifier}</span><span class="mx-2">|</span><span>UUID: ${n.uuid.substring(0,8)}... <i class="copy-btn" onclick="copyToClipboard('${n.uuid}', 'UUID')">📋</i></span></div></div><div class="flex gap-2 flex-wrap">${i?`<button onclick="apiAction('${n.uuid}','unsuspend','servers')" class="bg-green-600 hover:bg-green-700 text-white px-3 py-1.5 rounded-md text-sm">Unsuspend</button>`:`<button onclick="apiAction('${n.uuid}','suspend','servers')" class="bg-red-600 hover:bg-red-700 text-white px-3 py-1.5 rounded-md text-sm">Suspend</button>`}<button onclick="confirmAndAct('${n.uuid}','reinstall','reinstall')" class="bg-yellow-600 hover:bg-yellow-700 text-white px-3 py-1.5 rounded-md text-sm">Reinstall</button><button onclick="confirmAndAct('${n.uuid}','rebuild','rebuild')" class="bg-blue-600 hover:bg-blue-700 text-white px-3 py-1.5 rounded-md text-sm">Rebuild</button></div></div>`});const r=document.getElementById("server-pagination");r.innerHTML="";const{current_page:a,total_pages:s,prev_page:d,next_page:l}=e;if(s>1){let t="";t+=d?`<a href="#" onclick="loadServers(${a-1});return false;" class="px-3 py-1.5 bg-gray-700 hover:bg-gray-600 rounded-md">&laquo; Prev</a>`:`<span class="px-3 py-1.5 bg-gray-800 text-gray-500 rounded-md cursor-not-allowed">&laquo; Prev</span>`,t+=`<span class="px-3 py-1.5">Page ${a} of ${s}</span>`,t+=l?`<a href="#" onclick="loadServers(${a+1});return false;" class="px-3 py-1.5 bg-gray-700 hover:bg-gray-600 rounded-md">Next &raquo;</a>`:`<span class="px-3 py-1.5 bg-gray-800 text-gray-500 rounded-md cursor-not-allowed">Next &raquo;</span>`,r.innerHTML=t}},renderUsers=t=>{const e=document.getElementById("user-list");e.innerHTML="",t.forEach(t=>{const o=t.attributes;e.innerHTML+=`<div class="content-card p-3 rounded-md flex justify-between items-center text-sm"><div class="font-mono"><strong class="text-white">${o.username}</strong> (${o.first_name} ${o.last_name})<br><span class="text-gray-400">${o.email} <i class="copy-btn" onclick="copyToClipboard('${o.email}', 'Email')">📋</i></span></div><div class="text-gray-400">ID: ${o.id}</div></div>`})},renderNodes=t=>{const e=document.getElementById("node-list");e.innerHTML="",t.forEach(t=>{const o=t.attributes,n=o.allocated_resources,i=(n.memory/o.memory*100).toFixed(1),s=(n.disk/o.disk*100).toFixed(1);e.innerHTML+=`<div class="content-card p-4 rounded-lg"><h3 class="font-bold text-lg text-white mb-2">${o.name}</h3><div class="text-sm space-y-2"><div class="w-full bg-gray-700 rounded-full h-2.5"><div class="bg-blue-500 h-2.5 rounded-full" style="width:${i}%"></div></div><p>Memory: ${n.memory} / ${o.memory} MB (${i}%)</p><div class="w-full bg-gray-700 rounded-full h-2.5"><div class="bg-green-500 h-2.5 rounded-full" style="width:${s}%"></div></div><p>Disk: ${n.disk} / ${o.disk} MB (${s}%)</p><p>Servers: ${o.server_count}</p></div></div>`})};const loadServers=async t=>(document.getElementById("servers-loader").style.display="flex",document.getElementById("server-list").innerHTML="",document.getElementById("server-pagination").innerHTML="",history.pushState(null,null,`${window.location.pathname}?${currentParams()}`),fetch(`/api/servers?${currentParams()}`).then(t=>t.json()).then(t=>{document.getElementById("servers-loader").style.display="none",t.error?showToast(t.error,"error"):(renderServers(t.data,t.pagination),history.pushState(null,null,`?page=${t.pagination.current_page}&${currentParams(1)}`))}).catch(t=>{console.error("Error loading servers:",t),showToast("Failed to load servers.","error"),document.getElementById("servers-loader").style.display="none"}));function currentParams(t=0){const e=new URLSearchParams(window.location.search);return document.getElementById("search-form")&&new FormData(document.getElementById("search-form")).forEach((o,n)=>e.set(n,o)),t&&e.delete("page"),e.toString()}async function loadData(t,e,o,n){try{document.getElementById(`${t}-loader`).style.display="flex",document.getElementById(`${t}-list`).innerHTML="";let s=await fetch(`/api/${e}`);if(!s.ok)throw new Error(`HTTP error! status: ${s.status}`);let a=await s.json();a.error?(showToast(a.error,"error"),document.getElementById(`${t}-loader`).style.display="none"):o(a.data)}catch(e){console.error(`Error loading ${t}:`,e),showToast(`Failed to load ${t}.`,"error")}finally{document.getElementById(`${t}-loader`).style.display="none"}}async function checkApiStatus(){const t=document.getElementById("api-status");try{let e=await fetch("/api/health");if(!e.ok)throw new Error("API check failed");let o=await e.json();"ok"===o.status?(t.innerHTML='<div class="h-2 w-2 rounded-full bg-green-500"></div><span>Connected</span>',t.classList.remove("text-red-400"),t.classList.add("text-green-400")):(t.innerHTML='<div class="h-2 w-2 rounded-full bg-red-500"></div><span>Error</span>',t.classList.remove("text-green-400"),t.classList.add("text-red-400"))}catch(e){console.error("API Health Check Failed:",e),t.innerHTML='<div class="h-2 w-2 rounded-full bg-red-500"></div><span>Disconnected</span>',t.classList.remove("text-green-400"),t.classList.add("text-red-400")}}document.addEventListener("DOMContentLoaded",()=>{const t=new URLSearchParams(window.location.search).get("page")||1;loadServers(t),loadData("users","users",renderUsers),loadData("nodes","nodes",renderNodes),checkApiStatus(),setInterval(checkApiStatus,6e4),document.getElementById("search-form").addEventListener("submit",t=>{t.preventDefault(),loadServers(1)})});</script></body></html>
"""

# --- Routes ---
@app.route('/login', methods=['GET', 'POST'])
def login():
    if session.get('logged_in'):
        return redirect('/')
    if request.method == 'POST':
        if request.form.get('username') == app.config['ADMIN_USERNAME'] and \
           request.form.get('password') == app.config['ADMIN_PASSWORD']:
            session['logged_in'] = True
            session['username'] = app.config['ADMIN_USERNAME']
            session['_csrf_token'] = secrets.token_hex(16)
            logger.info(f"Successful login for '{session['username']}' from {request.remote_addr}")
            return redirect('/')
        else:
            logger.warning(f"Failed login attempt for '{request.form.get('username')}' from {request.remote_addr}")
            flash('Invalid username or password.', 'error')
    return render_template_string(LOGIN_TEMPLATE)

@app.route('/logout')
def logout():
    session.clear()
    return redirect('/login')

@app.route('/')
@login_required
def dashboard():
    # Initial page load renders the template. Data is fetched via API calls from the frontend.
    # We can still pass some initial stats if we want.
    servers_data, _ = api_client.get_paged_data('servers', params={'per_page': 1})
    users_data, _ = api_client.get_paged_data('users', params={'per_page': 1})
    nodes_data, _ = api_client.get_paged_data('nodes', params={'per_page': 1})

    stats = {
        'total_servers': servers_data.get('meta', {}).get('pagination', {}).get('total', 'N/A'),
        'total_users': users_data.get('meta', {}).get('pagination', {}).get('total', 'N/A'),
        'total_nodes': nodes_data.get('meta', {}).get('pagination', {}).get('total', 'N/A'),
        'panel_version': users_data.get('meta', {}).get('pterodactyl', {}).get('version', 'N/A')
    }
    return render_template_string(DASHBOARD_TEMPLATE, stats=stats)

# --- API Endpoints for Frontend ---

@app.route('/api/health')
@login_required
@rate_limit(limit=10)
def api_health_check(): # Feature 9: API Health Indicator
    _, error = api_client.get_paged_data('users', params={'per_page': 1})
    if error:
        return jsonify({"status": "error", "message": error}), 503
    return jsonify({"status": "ok"})

@app.route('/api/servers')
@login_required
@rate_limit(limit=60)
def get_servers(): # Feature 4 & 5: Pagination and Search/Filter
    page = request.args.get('page', 1, type=int)
    search_query = request.args.get('q', '').strip()
    suspended_filter = request.args.get('suspended', '').strip()

    params = {'page': page, 'per_page': 10, 'include': 'user'}
    if search_query:
        params['filter[name]'] = search_query
    if suspended_filter in ['true', 'false']:
        params['filter[suspended]'] = suspended_filter

    servers_data, error = api_client.get_paged_data('servers', params=params)
    if error:
        return jsonify({"error": error}), 500

    pagination_info = servers_data.get('meta', {}).get('pagination', {})
    response_data = {
        "data": servers_data.get('data', []),
        "pagination": {
            "total": pagination_info.get('total', 0),
            "per_page": pagination_info.get('per_page', 0),
            "current_page": pagination_info.get('current_page', 1),
            "total_pages": pagination_info.get('total_pages', 1),
            "prev_page": pagination_info.get('current_page', 1) > 1,
            "next_page": pagination_info.get('current_page', 1) < pagination_info.get('total_pages', 1)
        }
    }
    return jsonify(response_data)

@app.route('/api/users')
@login_required
@rate_limit()
def get_users(): # Feature 7: User Management
    users_data, error = api_client.get_all_data('users')
    if error:
        return jsonify({"error": error}), 500
    return jsonify(users_data)

@app.route('/api/nodes')
@login_required
@rate_limit()
def get_nodes(): # Feature 8: Enhanced Node Details
    nodes_data, n_err = api_client.get_all_data('nodes?include=servers')
    if n_err:
        return jsonify({"error": n_err}), 500
    
    # Process data to add server counts and allocated resources
    for node in nodes_data.get('data', []):
        attrs = node['attributes']
        servers_on_node = attrs.get('relationships', {}).get('servers', {}).get('data', [])
        attrs['server_count'] = len(servers_on_node)
    
    return jsonify(nodes_data)

@app.route('/control/<uuid>/<action>', methods=["POST"])
@login_required
@rate_limit(limit=15)
def control_server(uuid, action): # Feature 2 & 6: AJAX actions and more controls
    json_data = request.get_json()
    if not json_data or session.get('_csrf_token') != json_data.get('_csrf_token'):
        return jsonify({"error": "Invalid CSRF token."}), 403

    if not validate_uuid(uuid):
        return jsonify({"error": "Invalid server UUID format."}), 400

    allowed_actions = ['suspend', 'unsuspend', 'reinstall', 'rebuild']
    if action not in allowed_actions:
        return jsonify({"error": "Invalid action specified."}), 400

    _, error = api_client.control_server(uuid, action)

    if error:
        return jsonify({"error": f"Failed to {action} server: {error}"}), 500
    
    msg = f"Server successfully {action}{'ed' if action.endswith('d') else 'ed'}."
    if action == "unsuspend":
        msg = "Server successfully unsuspended."

    return jsonify({"message": msg})

# --- Error Handlers ---
@app.errorhandler(404)
def not_found(error):
    return "<h1>404 Not Found</h1><p>The page you are looking for does not exist.</p><a href='/'>Go Home</a>", 404

@app.errorhandler(500)
def server_error(error):
    logger.error(f"Server Error: {error}")
    return "<h1>500 Internal Server Error</h1><p>Something went wrong on our end.</p>", 500

if __name__ == '__main__':
    print("🚀 Starting Professional Pterodactyl Control Dashboard...")
    print(f"🔗 Panel URL: {app.config['PANEL_URL']}")
    print("🔐 Admin User: " + app.config['ADMIN_USERNAME'])
    app.run(host="0.0.0.0", port=8080, debug=False)
