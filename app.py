from flask import Flask, render_template_string, request, redirect, flash, session, jsonify
import requests
import os
import logging
from datetime import datetime, timedelta
import secrets
import re
import time
from functools import wraps

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

app = Flask(__name__)
app.secret_key = os.getenv("SECRET_KEY", secrets.token_hex(32))

# Configuration
PANEL_URL = os.getenv("PANEL_URL", "https://gamep.cloudcrash.shop")
API_KEY = os.getenv("API_KEY")
ADMIN_USERNAME = os.getenv("ADMIN_USERNAME", "admin")
ADMIN_PASSWORD = os.getenv("ADMIN_PASSWORD", "admin123")

if not API_KEY:
    logger.error("API_KEY environment variable is required!")
    exit(1)

headers = {
    "Authorization": f"Bearer {API_KEY}",
    "Accept": "Application/vnd.pterodactyl.v1+json",
    "Content-Type": "application/json"
}

# Rate limiting
request_times = {}
RATE_LIMIT = 60  # requests per minute

def rate_limit(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        client_ip = request.remote_addr
        current_time = time.time()
        
        if client_ip not in request_times:
            request_times[client_ip] = []
        
        # Remove old requests
        request_times[client_ip] = [req_time for req_time in request_times[client_ip] 
                                   if current_time - req_time < 60]
        
        if len(request_times[client_ip]) >= RATE_LIMIT:
            return jsonify({"error": "Rate limit exceeded"}), 429
        
        request_times[client_ip].append(current_time)
        return f(*args, **kwargs)
    return decorated_function

def login_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not session.get('logged_in'):
            return redirect('/login')
        return f(*args, **kwargs)
    return decorated_function

def validate_uuid(uuid_string):
    """Validate UUID format"""
    uuid_pattern = re.compile(r'^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$', re.IGNORECASE)
    return bool(uuid_pattern.match(uuid_string))

def make_api_request(endpoint, method='GET', data=None):
    """Make API request with error handling"""
    try:
        url = f"{PANEL_URL}/api/application/{endpoint}"
        
        if method == 'GET':
            response = requests.get(url, headers=headers, timeout=10)
        elif method == 'POST':
            response = requests.post(url, headers=headers, json=data, timeout=10)
        elif method == 'PATCH':
            response = requests.patch(url, headers=headers, json=data, timeout=10)
        elif method == 'DELETE':
            response = requests.delete(url, headers=headers, timeout=10)
        
        if response.status_code == 429:
            logger.warning("API rate limit hit")
            return None, "API rate limit exceeded"
        
        response.raise_for_status()
        return response.json() if response.content else {}, None
        
    except requests.exceptions.Timeout:
        logger.error(f"API request timeout: {endpoint}")
        return None, "Request timeout"
    except requests.exceptions.RequestException as e:
        logger.error(f"API request failed: {endpoint} - {str(e)}")
        return None, f"API request failed: {str(e)}"

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form.get('username', '').strip()
        password = request.form.get('password', '').strip()
        
        if username == ADMIN_USERNAME and password == ADMIN_PASSWORD:
            session['logged_in'] = True
            session['login_time'] = datetime.now().isoformat()
            logger.info(f"Successful login from {request.remote_addr}")
            flash('Successfully logged in!', 'success')
            return redirect('/')
        else:
            logger.warning(f"Failed login attempt from {request.remote_addr}")
            flash('Invalid credentials!', 'error')
    
    login_html = """
    <!DOCTYPE html>
    <html lang="en">
    <head>
        <meta charset="UTF-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <title>Login - Pterodactyl Dashboard</title>
        <script src="https://cdn.tailwindcss.com"></script>
    </head>
    <body class="bg-gradient-to-br from-blue-900 via-purple-900 to-indigo-900 min-h-screen flex items-center justify-center">
        <div class="bg-white/10 backdrop-blur-lg rounded-2xl p-8 w-full max-w-md shadow-2xl">
            <h1 class="text-3xl font-bold text-white text-center mb-8">🛠️ Pterodactyl Dashboard</h1>
            
            {% with messages = get_flashed_messages(with_categories=true) %}
                {% if messages %}
                    {% for category, message in messages %}
                        <div class="mb-4 p-3 rounded-lg {% if category == 'error' %}bg-red-500/20 text-red-200{% else %}bg-green-500/20 text-green-200{% endif %}">
                            {{ message }}
                        </div>
                    {% endfor %}
                {% endif %}
            {% endwith %}
            
            <form method="POST" class="space-y-6">
                <div>
                    <label class="block text-white mb-2">Username</label>
                    <input type="text" name="username" required 
                           class="w-full p-3 rounded-lg bg-white/20 text-white placeholder-white/60 border border-white/30 focus:border-white/60 focus:outline-none">
                </div>
                <div>
                    <label class="block text-white mb-2">Password</label>
                    <input type="password" name="password" required 
                           class="w-full p-3 rounded-lg bg-white/20 text-white placeholder-white/60 border border-white/30 focus:border-white/60 focus:outline-none">
                </div>
                <button type="submit" class="w-full bg-blue-600 hover:bg-blue-700 text-white font-bold py-3 px-4 rounded-lg transition-colors">
                    Login
                </button>
            </form>
        </div>
    </body>
    </html>
    """
    return render_template_string(login_html)

@app.route('/logout')
def logout():
    session.clear()
    flash('Successfully logged out!', 'success')
    return redirect('/login')

@app.route('/')
@login_required
@rate_limit
def dashboard():
    try:
        # Fetch data from API
        servers_data, servers_error = make_api_request("servers")
        nodes_data, nodes_error = make_api_request("nodes")
        users_data, users_error = make_api_request("users")
        
        if servers_error or nodes_error or users_error:
            error_msg = f"API Errors: {servers_error or ''} {nodes_error or ''} {users_error or ''}".strip()
            flash(f"Warning: {error_msg}", 'error')
            
        # Calculate statistics
        total_servers = len(servers_data.get('data', [])) if servers_data else 0
        total_users = len(users_data.get('data', [])) if users_data else 0
        total_nodes = len(nodes_data.get('data', [])) if nodes_data else 0
        
        suspended_servers = 0
        online_servers = 0
        
        # Generate server cards
        server_cards = ""
        if servers_data and 'data' in servers_data:
            for server in servers_data['data']:
                attrs = server['attributes']
                name = attrs.get('name', 'Unknown')
                uuid = attrs.get('uuid', '')
                identifier = attrs.get('identifier', '')
                suspended = attrs.get('suspended', False)
                node_id = attrs.get('node', 'N/A')
                
                if suspended:
                    suspended_servers += 1
                else:
                    online_servers += 1
                
                status_badge = """
                <span class="px-2 py-1 rounded-full text-xs font-semibold bg-red-100 text-red-800">Suspended</span>
                """ if suspended else """
                <span class="px-2 py-1 rounded-full text-xs font-semibold bg-green-100 text-green-800">Online</span>
                """
                
                suspend_button = f"""
                <form method="POST" action="/control/{uuid}/unsuspend" class="inline" onsubmit="return confirm('Are you sure you want to unsuspend this server?')">
                    <button class="bg-green-500 hover:bg-green-600 text-white px-3 py-1 rounded-lg text-sm transition-colors">
                        Unsuspend
                    </button>
                </form>
                """ if suspended else f"""
                <form method="POST" action="/control/{uuid}/suspend" class="inline" onsubmit="return confirm('Are you sure you want to suspend this server?')">
                    <button class="bg-red-500 hover:bg-red-600 text-white px-3 py-1 rounded-lg text-sm transition-colors">
                        Suspend
                    </button>
                </form>
                """
                
                server_cards += f"""
                <div class="bg-white/10 backdrop-blur-lg rounded-xl p-6 border border-white/20 hover:border-white/40 transition-all">
                    <div class="flex justify-between items-start mb-3">
                        <h3 class="font-bold text-white text-lg">{name}</h3>
                        {status_badge}
                    </div>
                    <div class="text-gray-300 text-sm space-y-1 mb-4">
                        <p><span class="font-medium">ID:</span> {identifier}</p>
                        <p><span class="font-medium">Node:</span> {node_id}</p>
                        <p><span class="font-medium">UUID:</span> {uuid[:8]}...</p>
                    </div>
                    <div class="flex gap-2">
                        {suspend_button}
                        <button onclick="viewServerDetails('{uuid}')" 
                                class="bg-blue-500 hover:bg-blue-600 text-white px-3 py-1 rounded-lg text-sm transition-colors">
                            Details
                        </button>
                    </div>
                </div>
                """
        
        # Generate node cards
        node_cards = ""
        if nodes_data and 'data' in nodes_data:
            for node in nodes_data['data']:
                attrs = node['attributes']
                name = attrs.get('name', 'Unknown')
                location = attrs.get('location_id', 'N/A')
                memory = attrs.get('memory', 0)
                disk = attrs.get('disk', 0)
                
                node_cards += f"""
                <div class="bg-white/10 backdrop-blur-lg rounded-xl p-6 border border-white/20">
                    <h3 class="font-bold text-white text-lg mb-2">{name}</h3>
                    <div class="text-gray-300 text-sm space-y-1">
                        <p><span class="font-medium">Location:</span> {location}</p>
                        <p><span class="font-medium">Memory:</span> {memory} MB</p>
                        <p><span class="font-medium">Disk:</span> {disk} MB</p>
                    </div>
                </div>
                """

        html = f"""
        <!DOCTYPE html>
        <html lang="en">
        <head>
            <meta charset="UTF-8">
            <meta name="viewport" content="width=device-width, initial-scale=1.0">
            <title>Pterodactyl Control Dashboard</title>
            <script src="https://cdn.tailwindcss.com"></script>
            <style>
                .stat-card {{
                    background: linear-gradient(135deg, rgba(255,255,255,0.1), rgba(255,255,255,0.05));
                    backdrop-filter: blur(10px);
                    border: 1px solid rgba(255,255,255,0.2);
                }}
            </style>
        </head>
        <body class="bg-gradient-to-br from-blue-900 via-purple-900 to-indigo-900 min-h-screen text-white">
            <!-- Navigation -->
            <nav class="bg-black/20 backdrop-blur-lg border-b border-white/10">
                <div class="max-w-7xl mx-auto px-4 py-4">
                    <div class="flex justify-between items-center">
                        <h1 class="text-2xl font-bold">🛠️ Pterodactyl Dashboard</h1>
                        <div class="flex items-center gap-4">
                            <span class="text-sm text-gray-300">Welcome, Admin</span>
                            <a href="/logout" class="bg-red-500 hover:bg-red-600 px-4 py-2 rounded-lg text-sm transition-colors">
                                Logout
                            </a>
                        </div>
                    </div>
                </div>
            </nav>

            <div class="max-w-7xl mx-auto py-8 px-4">
                <!-- Flash Messages -->
                {% with messages = get_flashed_messages(with_categories=true) %}
                    {% if messages %}
                        {% for category, message in messages %}
                            <div class="mb-6 p-4 rounded-lg {% if category == 'error' %}bg-red-500/20 border border-red-500/50 text-red-200{% else %}bg-green-500/20 border border-green-500/50 text-green-200{% endif %}">
                                {{ message }}
                            </div>
                        {% endfor %}
                    {% endif %}
                {% endwith %}

                <!-- Statistics Cards -->
                <div class="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-6 mb-8">
                    <div class="stat-card rounded-xl p-6 text-center">
                        <div class="text-3xl font-bold text-blue-400">{total_servers}</div>
                        <div class="text-gray-300">Total Servers</div>
                    </div>
                    <div class="stat-card rounded-xl p-6 text-center">
                        <div class="text-3xl font-bold text-green-400">{online_servers}</div>
                        <div class="text-gray-300">Online Servers</div>
                    </div>
                    <div class="stat-card rounded-xl p-6 text-center">
                        <div class="text-3xl font-bold text-red-400">{suspended_servers}</div>
                        <div class="text-gray-300">Suspended</div>
                    </div>
                    <div class="stat-card rounded-xl p-6 text-center">
                        <div class="text-3xl font-bold text-purple-400">{total_users}</div>
                        <div class="text-gray-300">Total Users</div>
                    </div>
                </div>

                <!-- Tabs -->
                <div class="mb-6">
                    <div class="border-b border-white/20">
                        <nav class="-mb-px flex space-x-8">
                            <button onclick="showTab('servers')" id="servers-tab" 
                                    class="tab-button border-b-2 border-blue-500 text-blue-400 py-2 px-1 font-medium text-sm">
                                Servers
                            </button>
                            <button onclick="showTab('nodes')" id="nodes-tab" 
                                    class="tab-button border-b-2 border-transparent text-gray-400 hover:text-gray-300 py-2 px-1 font-medium text-sm">
                                Nodes
                            </button>
                        </nav>
                    </div>
                </div>

                <!-- Servers Tab -->
                <div id="servers-content" class="tab-content">
                    <div class="flex justify-between items-center mb-6">
                        <h2 class="text-2xl font-semibold">Server Management</h2>
                        <button onclick="refreshData()" class="bg-blue-500 hover:bg-blue-600 px-4 py-2 rounded-lg transition-colors">
                            🔄 Refresh
                        </button>
                    </div>
                    <div class="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6">
                        {server_cards}
                    </div>
                </div>

                <!-- Nodes Tab -->
                <div id="nodes-content" class="tab-content hidden">
                    <h2 class="text-2xl font-semibold mb-6">Node Information</h2>
                    <div class="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6">
                        {node_cards}
                    </div>
                </div>
            </div>

            <!-- Server Details Modal -->
            <div id="serverModal" class="fixed inset-0 bg-black/50 backdrop-blur-sm hidden items-center justify-center z-50">
                <div class="bg-white/10 backdrop-blur-lg rounded-2xl p-6 w-full max-w-2xl mx-4 border border-white/20">
                    <div class="flex justify-between items-center mb-4">
                        <h3 class="text-xl font-bold">Server Details</h3>
                        <button onclick="closeModal()" class="text-gray-400 hover:text-white">✕</button>
                    </div>
                    <div id="serverDetails" class="text-gray-300">
                        Loading...
                    </div>
                </div>
            </div>

            <script>
                function showTab(tabName) {{
                    // Hide all tab contents
                    document.querySelectorAll('.tab-content').forEach(content => {{
                        content.classList.add('hidden');
                    }});
                    
                    // Remove active state from all tabs
                    document.querySelectorAll('.tab-button').forEach(button => {{
                        button.classList.remove('border-blue-500', 'text-blue-400');
                        button.classList.add('border-transparent', 'text-gray-400');
                    }});
                    
                    // Show selected tab content
                    document.getElementById(tabName + '-content').classList.remove('hidden');
                    
                    // Add active state to selected tab
                    const activeTab = document.getElementById(tabName + '-tab');
                    activeTab.classList.remove('border-transparent', 'text-gray-400');
                    activeTab.classList.add('border-blue-500', 'text-blue-400');
                }}

                function viewServerDetails(uuid) {{
                    document.getElementById('serverModal').classList.remove('hidden');
                    document.getElementById('serverModal').classList.add('flex');
                    
                    fetch(`/api/server/${{uuid}}`)
                        .then(response => response.json())
                        .then(data => {{
                            if (data.error) {{
                                document.getElementById('serverDetails').innerHTML = `<p class="text-red-400">Error: ${{data.error}}</p>`;
                            }} else {{
                                const server = data.attributes;
                                document.getElementById('serverDetails').innerHTML = `
                                    <div class="space-y-3">
                                        <div><strong>Name:</strong> ${{server.name}}</div>
                                        <div><strong>UUID:</strong> ${{server.uuid}}</div>
                                        <div><strong>Identifier:</strong> ${{server.identifier}}</div>
                                        <div><strong>Status:</strong> <span class="${{server.suspended ? 'text-red-400' : 'text-green-400'}}">${{server.suspended ? 'Suspended' : 'Active'}}</span></div>
                                        <div><strong>Node:</strong> ${{server.node}}</div>
                                        <div><strong>Created:</strong> ${{new Date(server.created_at).toLocaleString()}}</div>
                                        <div><strong>Updated:</strong> ${{new Date(server.updated_at).toLocaleString()}}</div>
                                    </div>
                                `;
                            }}
                        }})
                        .catch(error => {{
                            document.getElementById('serverDetails').innerHTML = `<p class="text-red-400">Error loading server details</p>`;
                        }});
                }}

                function closeModal() {{
                    document.getElementById('serverModal').classList.add('hidden');
                    document.getElementById('serverModal').classList.remove('flex');
                }}

                function refreshData() {{
                    location.reload();
                }}

                // Close modal when clicking outside
                document.getElementById('serverModal').addEventListener('click', function(e) {{
                    if (e.target === this) {{
                        closeModal();
                    }}
                }});
            </script>
        </body>
        </html>
        """
        return render_template_string(html)

    except Exception as e:
        logger.error(f"Dashboard error: {str(e)}")
        return render_template_string("""
        <div class="min-h-screen bg-gradient-to-br from-red-900 to-red-700 flex items-center justify-center">
            <div class="bg-white/10 backdrop-blur-lg rounded-2xl p-8 text-center text-white">
                <h1 class="text-2xl font-bold mb-4">⚠️ System Error</h1>
                <p class="text-gray-300">{{ error_message }}</p>
                <a href="/" class="mt-4 inline-block bg-blue-500 hover:bg-blue-600 px-4 py-2 rounded-lg transition-colors">
                    Try Again
                </a>
            </div>
        </div>
        """), 500

@app.route('/api/server/<uuid>')
@login_required
@rate_limit
def get_server_details(uuid):
    if not validate_uuid(uuid):
        return jsonify({"error": "Invalid UUID format"}), 400
    
    server_data, error = make_api_request(f"servers/{uuid}")
    if error:
        return jsonify({"error": error}), 500
    
    return jsonify(server_data.get('attributes', {}))

@app.route('/control/<uuid>/<action>', methods=["POST"])
@login_required
@rate_limit
def control_server(uuid, action):
    if not validate_uuid(uuid):
        flash("Invalid server UUID format", 'error')
        return redirect('/')
    
    if action not in ['suspend', 'unsuspend']:
        flash("Invalid action specified", 'error')
        return redirect('/')
    
    endpoint = f"servers/{uuid}/{action}"
    _, error = make_api_request(endpoint, 'POST')
    
    if error:
        flash(f"Failed to {action} server: {error}", 'error')
        logger.error(f"Failed to {action} server {uuid}: {error}")
    else:
        flash(f"Server successfully {'suspended' if action == 'suspend' else 'unsuspended'}!", 'success')
        logger.info(f"Server {uuid} {action}ed by admin from {request.remote_addr}")
    
    return redirect('/')

@app.route('/api/stats')
@login_required
@rate_limit
def get_stats():
    """API endpoint for dashboard statistics"""
    try:
        servers_data, _ = make_api_request("servers")
        users_data, _ = make_api_request("users")
        nodes_data, _ = make_api_request("nodes")
        
        stats = {
            'servers': len(servers_data.get('data', [])) if servers_data else 0,
            'users': len(users_data.get('data', [])) if users_data else 0,
            'nodes': len(nodes_data.get('data', [])) if nodes_data else 0,
            'timestamp': datetime.now().isoformat()
        }
        
        return jsonify(stats)
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.errorhandler(404)
def not_found(error):
    return render_template_string("""
    <div class="min-h-screen bg-gradient-to-br from-gray-900 to-gray-700 flex items-center justify-center">
        <div class="bg-white/10 backdrop-blur-lg rounded-2xl p-8 text-center text-white">
            <h1 class="text-6xl font-bold mb-4">404</h1>
            <p class="text-gray-300 mb-6">Page not found</p>
            <a href="/" class="bg-blue-500 hover:bg-blue-600 px-6 py-3 rounded-lg transition-colors">
                Go Home
            </a>
        </div>
    </div>
    """), 404

@app.errorhandler(500)
def server_error(error):
    return render_template_string("""
    <div class="min-h-screen bg-gradient-to-br from-red-900 to-red-700 flex items-center justify-center">
        <div class="bg-white/10 backdrop-blur-lg rounded-2xl p-8 text-center text-white">
            <h1 class="text-6xl font-bold mb-4">500</h1>
            <p class="text-gray-300 mb-6">Internal server error</p>
            <a href="/" class="bg-blue-500 hover:bg-blue-600 px-6 py-3 rounded-lg transition-colors">
                Go Home
            </a>
        </div>
    </div>
    """), 500

if __name__ == '__main__':
    print("🚀 Starting Pterodactyl Control Dashboard...")
    print(f"📊 Panel URL: {PANEL_URL}")
    print(f"🔐 Admin Username: {ADMIN_USERNAME}")
    print("⚠️  Make sure to set proper environment variables in production!")
    
    app.run(host="0.0.0.0", port=8080, debug=False)
