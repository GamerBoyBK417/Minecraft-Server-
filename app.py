from flask import Flask, render_template_string, request, redirect, flash, session, jsonify
from dotenv import load_dotenv
import requests
import os
import logging
import secrets
import re
import time
import json
from datetime import datetime, timedelta
from functools import wraps
from urllib.parse import urlparse
from collections import defaultdict

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
    SECRET_KEY = os.getenv("SECRET_KEY", secrets.token_hex(32))
    SESSION_TIMEOUT = int(os.getenv("SESSION_TIMEOUT", "3600"))  # 1 hour default
    MAX_LOGIN_ATTEMPTS = int(os.getenv("MAX_LOGIN_ATTEMPTS", "5"))
    
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

# --- Enhanced Security ---

# Login attempt tracking
login_attempts = defaultdict(list)
blocked_ips = {}

def is_ip_blocked(ip):
    if ip in blocked_ips:
        if datetime.now() < blocked_ips[ip]:
            return True
        else:
            del blocked_ips[ip]
    return False

def add_login_attempt(ip):
    current_time = datetime.now()
    # Clean old attempts (older than 15 minutes)
    login_attempts[ip] = [attempt for attempt in login_attempts[ip] 
                         if current_time - attempt < timedelta(minutes=15)]
    
    login_attempts[ip].append(current_time)
    
    if len(login_attempts[ip]) >= Config.MAX_LOGIN_ATTEMPTS:
        # Block IP for 30 minutes
        blocked_ips[ip] = current_time + timedelta(minutes=30)
        logger.warning(f"IP {ip} blocked due to too many login attempts")
        return True
    return False

# --- Pterodactyl API Client ---

class PterodactylAPI:
    def __init__(self, panel_url, api_key):
        self.base_url = f"{panel_url}/api/application"
        self.headers = {
            "Authorization": f"Bearer {api_key}",
            "Accept": "Application/vnd.pterodactyl.v1+json",
            "Content-Type": "application/json"
        }
        self.cache = {}
        self.cache_timeout = 60  # seconds
    
    def _get_cache_key(self, endpoint, params=None):
        return f"{endpoint}_{json.dumps(params, sort_keys=True) if params else ''}"
    
    def _is_cache_valid(self, cache_key):
        if cache_key not in self.cache:
            return False
        return time.time() - self.cache[cache_key]['timestamp'] < self.cache_timeout
    
    def _request(self, endpoint, method='GET', data=None, params=None, use_cache=True):
        cache_key = self._get_cache_key(endpoint, params)
        
        # Check cache for GET requests
        if method == 'GET' and use_cache and self._is_cache_valid(cache_key):
            return self.cache[cache_key]['data'], None
        
        url = f"{self.base_url}/{endpoint}"
        try:
            response = requests.request(method, url, headers=self.headers, json=data, params=params, timeout=15)
            
            if response.status_code == 429:
                return None, "API rate limit hit. Please try again in a moment."
            
            response.raise_for_status()
            result = response.json() if response.content else {}
            
            # Cache GET requests
            if method == 'GET' and use_cache:
                self.cache[cache_key] = {
                    'data': result,
                    'timestamp': time.time()
                }
            
            return result, None
        
        except requests.exceptions.Timeout as e:
            logger.error(f"API Timeout: {method} {url} - {e}")
            return None, "Request to the panel API timed out."
        except requests.exceptions.HTTPError as e:
            logger.error(f"API HTTP Error: {method} {url} - {e.response.status_code} {e.response.text}")
            error_msg = f"API request failed with status {e.response.status_code}."
            try:
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
    
    def get_all_data(self, endpoint, params=None):
        all_data = []
        url = f"{self.base_url}/{endpoint}"
        if params is None:
            params = {}
        params['per_page'] = 100
        
        page_count = 0
        max_pages = 10 # Safety break to avoid infinite loops
        
        while url and page_count < max_pages:
            try:
                response = requests.get(url, headers=self.headers, params=params, timeout=15)
                response.raise_for_status()
                json_data = response.json()
                all_data.extend(json_data['data'])
                
                # The 'next' link includes all necessary params, so we clear ours for subsequent requests
                params = None 
                url = json_data.get('meta', {}).get('pagination', {}).get('links', {}).get('next')
                page_count += 1
            except requests.exceptions.RequestException as e:
                logger.error(f"Failed to fetch all data from {endpoint}: {e}")
                return None, f"Could not fetch all data from {endpoint}."
        
        # We need to manually construct the final meta object if we paged
        final_meta = json_data.get('meta', {}) if 'json_data' in locals() else {}
        if 'pagination' in final_meta:
            final_meta['pagination']['total'] = len(all_data)

        return {'data': all_data, 'meta': final_meta}, None
    
    def control_server(self, uuid, action, data=None):
        endpoint = f"servers/{uuid}/{action}"
        return self._request(endpoint, 'POST', data=data, use_cache=False)
    
    def create_server(self, data):
        return self._request("servers", 'POST', data=data, use_cache=False)
    
    def delete_server(self, uuid):
        return self._request(f"servers/{uuid}", 'DELETE', use_cache=False)
    
    def update_server(self, uuid, data):
        return self._request(f"servers/{uuid}/details", 'PATCH', data=data, use_cache=False)
    
    def create_user(self, data):
        return self._request("users", 'POST', data=data, use_cache=False)
    
    def delete_user(self, user_id):
        return self._request(f"users/{user_id}", 'DELETE', use_cache=False)

api_client = PterodactylAPI(app.config['PANEL_URL'], app.config['API_KEY'])

# --- Middleware & Decorators ---

request_times = {}

def rate_limit(limit=30, per=60):
    def decorator(f):
        @wraps(f)
        def wrapped(*args, **kwargs):
            client_ip = request.remote_addr
            current_time = time.time()
            if client_ip not in request_times:
                request_times[client_ip] = []
            
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
            flash('Please log in to access this page.', 'warning')
            return redirect('/login')
        
        # Check session timeout
        if 'login_time' in session:
            login_time = session['login_time']
            if isinstance(login_time, str): # Handle session data being stringified
                login_time = datetime.fromisoformat(login_time)
            if datetime.now() - login_time > timedelta(seconds=Config.SESSION_TIMEOUT):
                session.clear()
                flash('Session expired. Please log in again.', 'warning')
                return redirect('/login')
        
        session['login_time'] = datetime.now().isoformat() # Update timestamp on activity

        if '_csrf_token' not in session:
            session['_csrf_token'] = secrets.token_hex(16)
        return f(*args, **kwargs)
    return decorated_function

@app.after_request
def add_security_headers(response):
    response.headers['X-Content-Type-Options'] = 'nosniff'
    response.headers['X-Frame-Options'] = 'SAMEORIGIN'
    response.headers['X-XSS-Protection'] = '1; mode=block'
    response.headers['Strict-Transport-Security'] = 'max-age=31536000; includeSubDomains'
    response.headers['Content-Security-Policy'] = "default-src 'self'; script-src 'self' 'unsafe-inline' https://cdn.tailwindcss.com; style-src 'self' 'unsafe-inline'; font-src 'self'; img-src 'self' data:; connect-src 'self';"
    response.headers['Referrer-Policy'] = 'strict-origin-when-cross-origin'
    return response

# --- Utility Functions ---

def validate_uuid(uuid_string):
    uuid_pattern = re.compile(r'^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$', re.IGNORECASE)
    return bool(uuid_pattern.match(str(uuid_string)))

def validate_email(email):
    email_pattern = re.compile(r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$')
    return bool(email_pattern.match(email))

def sanitize_input(input_str, max_length=255):
    if not input_str:
        return ""
    return re.sub(r'[<>"\']', '', str(input_str))[:max_length]

def log_action(action, details=""):
    user = session.get('username', 'Anonymous')
    ip = request.remote_addr
    logger.info(f"Action: {action} | User: {user} | IP: {ip} | Details: {details}")

# --- Templates ---

LOGIN_TEMPLATE = """
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Admin Dashboard - Login</title>
    <script src="https://cdn.tailwindcss.com"></script>
    <style>
        body { background: linear-gradient(135deg, #667eea 0%, #764ba2 100%); }
        .glass { backdrop-filter: blur(16px); background: rgba(255, 255, 255, 0.1); border: 1px solid rgba(255, 255, 255, 0.2); }
    </style>
</head>
<body class="flex items-center justify-center min-h-screen">
    <div class="glass p-8 rounded-2xl shadow-2xl w-full max-w-md">
        <div class="text-center mb-8">
            <h1 class="text-3xl font-bold text-white mb-2">Admin Dashboard</h1>
            <p class="text-gray-200">Pterodactyl Control Panel</p>
        </div>
        
        {% with messages = get_flashed_messages(with_categories=true) %}
        {% if messages %}
            {% for category, message in messages %}
            <div class="mb-4 p-4 rounded-lg {% if category == 'error' %}bg-red-500/20 text-red-100 border border-red-400/30{% elif category == 'warning' %}bg-yellow-500/20 text-yellow-100 border border-yellow-400/30{% else %}bg-blue-500/20 text-blue-100 border border-blue-400/30{% endif %}">
                {{ message }}
            </div>
            {% endfor %}
        {% endif %}
        {% endwith %}
        
        <form method="POST" class="space-y-6">
            <div>
                <label class="block text-sm font-medium text-gray-200 mb-2">Username</label>
                <input type="text" name="username" required 
                       class="w-full p-3 bg-white/10 text-white rounded-lg border border-white/20 focus:outline-none focus:ring-2 focus:ring-white/50 placeholder-gray-300"
                       placeholder="Enter your username">
            </div>
            
            <div>
                <label class="block text-sm font-medium text-gray-200 mb-2">Password</label>
                <input type="password" name="password" required 
                       class="w-full p-3 bg-white/10 text-white rounded-lg border border-white/20 focus:outline-none focus:ring-2 focus:ring-white/50 placeholder-gray-300"
                       placeholder="Enter your password">
            </div>
            
            <button type="submit" 
                    class="w-full bg-white/20 hover:bg-white/30 text-white font-bold py-3 rounded-lg transition-all duration-300 transform hover:scale-105">
                Sign In
            </button>
        </form>
        
        <div class="mt-6 text-center text-sm text-gray-300">
            <p>Secure admin access only</p>
        </div>
    </div>
</body>
</html>
"""

DASHBOARD_TEMPLATE = """
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Pterodactyl Admin Dashboard</title>
    <script src="https://cdn.tailwindcss.com"></script>
    <style>
        body { background: linear-gradient(135deg, #1e3c72 0%, #2a5298 100%); min-height: 100vh; color: #e5e7eb; }
        .glass { backdrop-filter: blur(16px); background: rgba(255, 255, 255, 0.05); border: 1px solid rgba(255, 255, 255, 0.1); }
        .nav-glass { backdrop-filter: blur(20px); background: rgba(0, 0, 0, 0.2); border-bottom: 1px solid rgba(255, 255, 255, 0.1); }
        .tab-button.active { background: rgba(255, 255, 255, 0.15); color: white; }
        .toast { position: fixed; bottom: 20px; right: 20px; padding: 12px 20px; border-radius: 8px; z-index: 1000; color: white; opacity: 0; transform: translateY(20px); transition: all 0.3s ease; }
        .toast.show { opacity: 1; transform: translateY(0); }
        .toast.success { background: linear-gradient(135deg, #10b981, #059669); }
        .toast.error { background: linear-gradient(135deg, #ef4444, #dc2626); }
        .toast.warning { background: linear-gradient(135deg, #f59e0b, #d97706); }
        .loader { border: 4px solid rgba(255, 255, 255, 0.2); border-top: 4px solid white; border-radius: 50%; width: 32px; height: 32px; animation: spin 1s linear infinite; }
        @keyframes spin { 0% { transform: rotate(0deg); } 100% { transform: rotate(360deg); } }
        .stat-card { background: linear-gradient(135deg, rgba(255, 255, 255, 0.1), rgba(255, 255, 255, 0.05)); transition: all 0.3s ease; }
        .stat-card:hover { transform: translateY(-2px); background: linear-gradient(135deg, rgba(255, 255, 255, 0.15), rgba(255, 255, 255, 0.1)); }
        .modal { display: none; position: fixed; z-index: 1000; left: 0; top: 0; width: 100%; height: 100%; background: rgba(0, 0, 0, 0.6); backdrop-filter: blur(5px); }
        .modal.show { display: flex; align-items: center; justify-content: center; }
        .progress-bar { height: 6px; background: rgba(255, 255, 255, 0.2); border-radius: 3px; overflow: hidden; }
        .progress-fill { height: 100%; background: linear-gradient(90deg, #10b981, #059669); transition: width 0.3s ease; }
        .animate-fade-in { animation: fadeIn 0.5s ease; }
        @keyframes fadeIn { from { opacity: 0; transform: translateY(10px); } to { opacity: 1; transform: translateY(0); } }
        input, select, button { transition: all 0.2s ease-in-out; }
    </style>
</head>
<body class="text-gray-200">
    <div id="toast-container"></div>
    
    <!-- Navigation -->
    <nav class="nav-glass sticky top-0 z-50">
        <div class="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8">
            <div class="flex items-center justify-between h-16">
                <div class="flex items-center space-x-4">
                    <h1 class="font-bold text-xl text-white">🚀 Pterodactyl Admin</h1>
                    <div id="api-status" class="flex items-center gap-2 text-xs text-gray-300">
                        <div class="h-2 w-2 rounded-full bg-yellow-500 animate-pulse"></div>
                        <span>Checking...</span>
                    </div>
                </div>
                <div class="flex items-center gap-4">
                    <span class="text-sm text-gray-300 hidden md:block">Welcome, <strong>{{ session.username }}</strong></span>
                    <div class="text-xs text-gray-400 hidden lg:block">{{ current_time.strftime('%Y-%m-%d %H:%M') }}</div>
                    <a href="/logout" class="bg-red-500/20 hover:bg-red-500/40 text-red-100 px-4 py-2 rounded-lg text-sm font-medium">
                        Logout
                    </a>
                </div>
            </div>
        </div>
    </nav>

    <!-- Main Content -->
    <main class="max-w-7xl mx-auto py-6 px-4 sm:px-6 lg:px-8">
        <!-- Stats Cards -->
        <div class="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-6 mb-8">
            {% for key, value in stats.items() %}
            <div id="stat-{{key}}" class="stat-card p-6 rounded-xl text-center text-white">
                <p class="text-3xl font-bold mb-2">{{ value }}</p>
                <p class="text-sm opacity-80 capitalize">{{ key.replace('_', ' ') }}</p>
            </div>
            {% endfor %}
        </div>

        <!-- Main Dashboard -->
        <div class="glass rounded-xl p-4 md:p-6">
            <!-- Tab Navigation -->
            <div class="border-b border-white/20 mb-6">
                <div class="flex flex-wrap -mb-px gap-2">
                    <button id="servers-tab" onclick="showTab('servers')" class="tab-button px-4 py-2 rounded-t-lg text-sm font-medium">🖥️ Servers</button>
                    <button id="users-tab" onclick="showTab('users')" class="tab-button px-4 py-2 rounded-t-lg text-sm font-medium">👥 Users</button>
                    <button id="nodes-tab" onclick="showTab('nodes')" class="tab-button px-4 py-2 rounded-t-lg text-sm font-medium">🌐 Nodes</button>
                    <button id="logs-tab" onclick="showTab('logs')" class="tab-button px-4 py-2 rounded-t-lg text-sm font-medium">📊 Activity</button>
                </div>
            </div>

            <!-- Servers Tab -->
            <div id="servers-content" class="tab-content">
                <div class="flex flex-col lg:flex-row gap-4 justify-between items-start lg:items-center mb-6">
                    <h2 class="text-xl font-semibold text-white">Server Management</h2>
                    <form id="search-form" class="flex flex-wrap gap-2 w-full lg:w-auto">
                        <input type="search" name="q" placeholder="Search servers by name..." value="{{ request.args.get('q', '') }}" 
                               class="flex-grow lg:w-64 p-2 bg-white/10 border border-white/20 rounded-lg text-white placeholder-gray-300 text-sm">
                        <select name="suspended" class="p-2 bg-white/10 border border-white/20 rounded-lg text-white text-sm">
                            <option value="">All Statuses</option>
                            <option value="true" {% if request.args.get('suspended') == 'true' %}selected{% endif %}>Suspended</option>
                            <option value="false" {% if request.args.get('suspended') == 'false' %}selected{% endif %}>Active</option>
                        </select>
                        <button type="submit" class="bg-blue-500/30 hover:bg-blue-500/50 text-white px-4 py-2 rounded-lg text-sm">Filter</button>
                    </form>
                </div>
                <div id="server-list" class="space-y-4"></div>
                <div id="servers-loader" class="flex justify-center p-8"><div class="loader"></div></div>
                <div id="server-pagination" class="flex justify-between items-center mt-6 text-sm"></div>
            </div>

            <!-- Users Tab -->
            <div id="users-content" class="tab-content hidden">
                <div class="flex justify-between items-center mb-6">
                    <h2 class="text-xl font-semibold text-white">User Management</h2>
                    <button onclick="showModal('createUserModal')" class="bg-green-500/30 hover:bg-green-500/50 text-white px-4 py-2 rounded-lg text-sm">➕ Create User</button>
                </div>
                <div id="user-list" class="space-y-3"></div>
                <div id="users-loader" class="flex justify-center p-8"><div class="loader"></div></div>
            </div>

            <!-- Nodes Tab -->
            <div id="nodes-content" class="tab-content hidden">
                <h2 class="text-xl font-semibold text-white mb-6">Node Status & Resources</h2>
                <div id="node-list" class="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6"></div>
                <div id="nodes-loader" class="flex justify-center p-8"><div class="loader"></div></div>
            </div>

            <!-- Activity Log Tab -->
            <div id="logs-content" class="tab-content hidden">
                <div class="flex justify-between items-center mb-6">
                    <h2 class="text-xl font-semibold text-white">Recent Activity</h2>
                    <button onclick="refreshStats()" class="bg-purple-500/30 hover:bg-purple-500/50 text-white px-4 py-2 rounded-lg text-sm">Refresh Stats</button>
                </div>
                <div id="activity-log" class="space-y-3 max-h-96 overflow-y-auto pr-2"></div>
            </div>
        </div>
    </main>

    <!-- Modals -->
    <div id="createUserModal" class="modal">
        <div class="glass p-6 rounded-xl w-full max-w-md mx-4 animate-fade-in">
            <h3 class="text-lg font-semibold text-white mb-4">Create New User</h3>
            <form id="createUserForm" class="space-y-4">
                <input type="text" name="username" placeholder="Username" required class="w-full p-3 bg-white/10 text-white rounded-lg border border-white/20 placeholder-gray-300">
                <input type="email" name="email" placeholder="Email" required class="w-full p-3 bg-white/10 text-white rounded-lg border border-white/20 placeholder-gray-300">
                <input type="text" name="first_name" placeholder="First Name" required class="w-full p-3 bg-white/10 text-white rounded-lg border border-white/20 placeholder-gray-300">
                <input type="text" name="last_name" placeholder="Last Name" required class="w-full p-3 bg-white/10 text-white rounded-lg border border-white/20 placeholder-gray-300">
                <input type="password" name="password" placeholder="Password (leave blank for random)" class="w-full p-3 bg-white/10 text-white rounded-lg border border-white/20 placeholder-gray-300">
                <div class="flex gap-2">
                    <button type="submit" class="flex-1 bg-green-500/30 hover:bg-green-500/50 text-white py-2 rounded-lg">Create User</button>
                    <button type="button" onclick="hideModal('createUserModal')" class="flex-1 bg-gray-500/30 hover:bg-gray-500/50 text-white py-2 rounded-lg">Cancel</button>
                </div>
            </form>
        </div>
    </div>

    <script>
        const csrf_token = "{{ session._csrf_token }}";

        // --- Core Systems ---

        function showToast(message, type = 'success', duration = 4000) {
            const container = document.getElementById('toast-container');
            const toast = document.createElement('div');
            toast.className = `toast ${type}`;
            toast.textContent = message;
            container.appendChild(toast);
            setTimeout(() => toast.classList.add('show'), 10);
            setTimeout(() => {
                toast.classList.remove('show');
                setTimeout(() => container.removeChild(toast), 300);
            }, duration);
            logActivity(`Toast: ${message}`, type);
        }

        function logActivity(action, type = 'info') {
            const logContainer = document.getElementById('activity-log');
            const entry = document.createElement('div');
            const timestamp = new Date().toLocaleTimeString();
            
            entry.className = `glass p-3 rounded-lg animate-fade-in`;
            entry.innerHTML = `
                <p class="text-white text-sm"><strong>${action}</strong> - ${timestamp}</p>
                <p class="text-gray-300 text-xs capitalize">Status: ${type}</p>
            `;
            if (logContainer.firstChild) {
                logContainer.insertBefore(entry, logContainer.firstChild);
            } else {
                logContainer.appendChild(entry);
            }
            while (logContainer.children.length > 20) {
                logContainer.removeChild(logContainer.lastChild);
            }
        }

        async function fetchAPI(endpoint, options = {}) {
            options.headers = {
                'Content-Type': 'application/json',
                'X-CSRF-Token': csrf_token,
                ...options.headers,
            };
            
            try {
                const response = await fetch(endpoint, options);
                const data = await response.json();
                if (!response.ok) {
                    throw new Error(data.error || `HTTP error! status: ${response.status}`);
                }
                return data;
            } catch (error) {
                console.error(`Fetch error for ${endpoint}:`, error);
                showToast(error.message, 'error');
                throw error;
            }
        }

        function showTab(tabName) {
            document.querySelectorAll('.tab-content').forEach(content => content.classList.add('hidden'));
            document.querySelectorAll('.tab-button').forEach(button => button.classList.remove('active'));
            
            document.getElementById(`${tabName}-content`).classList.remove('hidden');
            document.getElementById(`${tabName}-tab`).classList.add('active');
            logActivity(`Viewed '${tabName}' tab`);
            
            const listElement = document.getElementById(`${tabName}-list`);
            const needsLoading = listElement && !listElement.innerHTML.trim();

            if (tabName === 'servers' && needsLoading) fetchServers();
            if (tabName === 'users' && needsLoading) fetchUsers();
            if (tabName === 'nodes' && needsLoading) fetchNodes();
        }

        function showModal(modalId) { document.getElementById(modalId).classList.add('show'); }
        function hideModal(modalId) { document.getElementById(modalId).classList.remove('show'); }

        // --- Data Fetching and Rendering ---

        async function checkApiStatus() {
            const statusDiv = document.getElementById('api-status');
            try {
                await fetchAPI('/api/status');
                statusDiv.innerHTML = `<div class="h-2 w-2 rounded-full bg-green-500"></div><span>API Connected</span>`;
                logActivity('API connection successful', 'success');
            } catch (error) {
                statusDiv.innerHTML = `<div class="h-2 w-2 rounded-full bg-red-500"></div><span>API Error</span>`;
                logActivity('API connection failed', 'error');
            }
        }

        async function fetchServers(page = 1, query = '', suspended = '') {
            const list = document.getElementById('server-list');
            const loader = document.getElementById('servers-loader');
            list.innerHTML = '';
            loader.style.display = 'flex';
            
            try {
                const data = await fetchAPI(`/api/servers?page=${page}&q=${encodeURIComponent(query)}&suspended=${suspended}`);
                renderServerList(data.servers.data);
                renderPagination(data.servers.meta.pagination, 'server-pagination', (p) => fetchServers(p, query, suspended));
                logActivity(`Fetched servers page ${page}`);
            } catch (error) {
                list.innerHTML = `<p class="text-center text-red-300 p-4">Failed to load servers.</p>`;
            } finally {
                loader.style.display = 'none';
            }
        }

        function renderServerList(servers) {
            const list = document.getElementById('server-list');
            if (servers.length === 0) {
                list.innerHTML = `<p class="text-center text-gray-300 p-4">No servers found.</p>`;
                return;
            }
            list.innerHTML = servers.map(server => {
                const s = server.attributes;
                return `
                <div class="glass p-3 rounded-lg flex flex-col md:flex-row items-center gap-4 animate-fade-in">
                    <div class="flex-grow w-full">
                        <p class="font-bold text-white">${s.name}</p>
                        <p class="text-xs text-gray-400">${s.uuid}</p>
                        <p class="text-sm text-gray-300 mt-1">Node: ${s.node}</p>
                    </div>
                    <div class="flex items-center gap-2 text-sm">
                        <span class="px-2 py-1 rounded-full text-xs ${s.suspended ? 'bg-yellow-500/20 text-yellow-200' : 'bg-green-500/20 text-green-200'}">
                            ${s.suspended ? 'Suspended' : 'Active'}
                        </span>
                    </div>
                    <div class="flex flex-wrap gap-2 justify-center">
                        <button onclick="controlServer('${s.uuid}', 'power', 'start')" class="bg-green-500/20 hover:bg-green-500/40 text-white px-3 py-1 rounded-md text-sm">Start</button>
                        <button onclick="controlServer('${s.uuid}', 'power', 'stop')" class="bg-yellow-500/20 hover:bg-yellow-500/40 text-white px-3 py-1 rounded-md text-sm">Stop</button>
                        <button onclick="controlServer('${s.uuid}', 'power', 'kill')" class="bg-red-500/20 hover:bg-red-500/40 text-white px-3 py-1 rounded-md text-sm">Kill</button>
                        <button onclick="deleteServer('${s.uuid}')" class="bg-red-700/30 hover:bg-red-700/50 text-white px-3 py-1 rounded-md text-sm">Delete</button>
                    </div>
                </div>
            `}).join('');
        }
        
        function renderPagination(pagination, containerId, pageClickHandler) {
            const container = document.getElementById(containerId);
            if (!pagination || pagination.total_pages <= 1) {
                container.innerHTML = '';
                return;
            }
            container.innerHTML = `
                <span class="text-gray-300">Page ${pagination.current_page} of ${pagination.total_pages} (${pagination.total} results)</span>
                <div class="flex gap-2">
                    <button ${pagination.current_page === 1 ? 'disabled' : ''} onclick="(${pageClickHandler})(${pagination.current_page - 1})" class="px-3 py-1 rounded-md bg-white/10 hover:bg-white/20 disabled:opacity-50 disabled:cursor-not-allowed">Prev</button>
                    <button ${pagination.current_page === pagination.total_pages ? 'disabled' : ''} onclick="(${pageClickHandler})(${pagination.current_page + 1})" class="px-3 py-1 rounded-md bg-white/10 hover:bg-white/20 disabled:opacity-50 disabled:cursor-not-allowed">Next</button>
                </div>
            `;
        }
        
        async function fetchUsers() {
            const list = document.getElementById('user-list');
            const loader = document.getElementById('users-loader');
            list.innerHTML = '';
            loader.style.display = 'flex';
            
            try {
                const data = await fetchAPI('/api/users');
                renderUserList(data.users.data);
                logActivity(`Fetched ${data.users.data.length} users`);
            } catch (error) {
                list.innerHTML = `<p class="text-center text-red-300 p-4">Failed to load users.</p>`;
            } finally {
                loader.style.display = 'none';
            }
        }

        function renderUserList(users) {
            const list = document.getElementById('user-list');
            if (users.length === 0) { list.innerHTML = `<p class="text-center text-gray-300 p-4">No users found.</p>`; return; }
            list.innerHTML = users.map(user => {
                const u = user.attributes;
                return `
                <div class="glass p-3 rounded-lg flex items-center gap-4 animate-fade-in">
                    <div class="flex-grow">
                        <p class="font-semibold text-white">${u.first_name} ${u.last_name} (${u.username})</p>
                        <p class="text-xs text-gray-400">${u.email}</p>
                    </div>
                    <span class="text-xs px-2 py-1 rounded-full ${u.root_admin ? 'bg-purple-500/30 text-purple-200' : 'bg-gray-500/30 text-gray-200'}">
                        ${u.root_admin ? 'Admin' : 'User'}
                    </span>
                    <button onclick="deleteUser(${u.id}, '${u.username}')" class="bg-red-700/30 hover:bg-red-700/50 text-white px-3 py-1 rounded-md text-sm">Delete</button>
                </div>
            `}).join('');
        }

        async function fetchNodes() {
            const list = document.getElementById('node-list');
            const loader = document.getElementById('nodes-loader');
            list.innerHTML = '';
            loader.style.display = 'flex';
            
            try {
                const data = await fetchAPI('/api/nodes');
                renderNodeList(data.nodes.data);
                logActivity(`Fetched ${data.nodes.data.length} nodes`);
            } catch (error) {
                list.innerHTML = `<p class="text-center text-red-300 p-4">Failed to load nodes.</p>`;
            } finally {
                loader.style.display = 'none';
            }
        }
        
        function renderNodeList(nodes) {
            const list = document.getElementById('node-list');
            if (nodes.length === 0) { list.innerHTML = `<p class="text-center text-gray-300 p-4">No nodes found.</p>`; return; }
            list.innerHTML = nodes.map(node => {
                const n = node.attributes;
                const mem_over = n.memory_overallocate || n.memory;
                const disk_over = n.disk_overallocate || n.disk;
                const memoryPercent = (n.memory / mem_over * 100).toFixed(1);
                const diskPercent = (n.disk / disk_over * 100).toFixed(1);
                return `
                <div class="glass p-5 rounded-xl text-white animate-fade-in">
                    <h3 class="font-bold text-lg mb-3">${n.name}</h3>
                    <div class="space-y-3 text-sm">
                        <div>
                            <div class="flex justify-between mb-1 text-xs">
                                <span>Memory</span>
                                <span>${(n.memory / 1024).toFixed(1)} / ${(mem_over / 1024).toFixed(1)} GB</span>
                            </div>
                            <div class="progress-bar"><div class="progress-fill bg-teal-400" style="width: ${memoryPercent}%"></div></div>
                        </div>
                        <div>
                            <div class="flex justify-between mb-1 text-xs">
                                <span>Disk</span>
                                <span>${(n.disk / 1024).toFixed(1)} / ${(disk_over / 1024).toFixed(1)} GB</span>
                            </div>
                            <div class="progress-bar"><div class="progress-fill bg-sky-400" style="width: ${diskPercent}%"></div></div>
                        </div>
                        <p class="text-xs text-gray-400 pt-2">Location: ${n.location_id} | ${n.maintenance_mode ? 'Maintenance' : 'Online'}</p>
                    </div>
                </div>
            `}).join('');
        }

        async function refreshStats() {
            showToast('Refreshing stats...', 'warning');
            try {
                const data = await fetchAPI('/api/stats');
                for (const [key, value] of Object.entries(data.stats)) {
                    const card = document.getElementById(`stat-${key}`);
                    if(card) card.querySelector('p:first-child').textContent = value;
                }
                showToast('Stats updated!', 'success');
            } catch (error) {
                // Error toast is already shown by fetchAPI
            }
        }

        // --- Action Handlers ---

        async function controlServer(uuid, action, signal) {
            showToast(`Sending '${signal}' command...`, 'warning');
            try {
                await fetchAPI(`/api/server/${uuid}/${action}`, {
                    method: 'POST',
                    body: JSON.stringify({ signal: signal })
                });
                showToast(`Successfully sent '${signal}' command.`, 'success');
                logActivity(`Server ${uuid}: Sent '${signal}' command`, 'success');
            } catch (error) {
                logActivity(`Server ${uuid}: Failed to send '${signal}' command`, 'error');
            }
        }
        
        async function deleteServer(uuid) {
            if (!confirm('Are you sure you want to permanently delete this server? This cannot be undone.')) return;
            showToast(`Deleting server ${uuid}...`, 'warning');
            try {
                await fetchAPI(`/api/server/${uuid}/delete`, { method: 'POST' });
                showToast('Server deleted successfully.', 'success');
                logActivity(`Server ${uuid}: Deleted`, 'success');
                fetchServers(1, document.querySelector('#search-form input[name=q]').value, document.querySelector('#search-form select[name=suspended]').value);
                refreshStats();
            } catch (error) {
                logActivity(`Server ${uuid}: Failed to delete`, 'error');
            }
        }

        async function deleteUser(userId, username) {
            if (!confirm(`Are you sure you want to delete user '${username}'? This cannot be undone.`)) return;
            showToast(`Deleting user ${username}...`, 'warning');
            try {
                await fetchAPI(`/api/users/${userId}`, { method: 'DELETE' });
                showToast('User deleted successfully.', 'success');
                logActivity(`User ${username} (ID: ${userId}) deleted`, 'success');
                fetchUsers();
                refreshStats();
            } catch (error) {
                logActivity(`Failed to delete user ${username}`, 'error');
            }
        }
        
        document.getElementById('createUserForm').addEventListener('submit', async function(e) {
            e.preventDefault();
            const formData = new FormData(this);
            const data = Object.fromEntries(formData.entries());
            if (!data.password) { // Pterodactyl requires a password, so generate one if blank
                data.password = Math.random().toString(36).slice(-12);
                showToast(`No password entered. Generated a temporary one: ${data.password}`, 'warning', 6000);
            }
            
            showToast('Creating user...', 'warning');
            try {
                await fetchAPI('/api/users', { method: 'POST', body: JSON.stringify(data) });
                showToast('User created successfully!', 'success');
                logActivity(`User ${data.username} created`, 'success');
                hideModal('createUserModal');
                this.reset();
                fetchUsers();
                refreshStats();
            } catch (error) {
                 logActivity(`Failed to create user ${data.username}`, 'error');
            }
        });
        
        document.getElementById('search-form').addEventListener('submit', function(e) {
            e.preventDefault();
            const formData = new FormData(this);
            const query = formData.get('q');
            const suspended = formData.get('suspended');
            fetchServers(1, query, suspended);
        });

        // --- Initial Load ---
        document.addEventListener('DOMContentLoaded', () => {
            logActivity("Dashboard loaded");
            showTab('servers');
            checkApiStatus();
        });
    </script>
</body>
</html>
"""

# --- Routes ---

@app.route('/login', methods=['GET', 'POST'])
def login():
    if session.get('logged_in'):
        return redirect('/')

    client_ip = request.remote_addr
    if is_ip_blocked(client_ip):
        flash('Your IP is temporarily blocked due to too many failed login attempts.', 'error')
        return render_template_string(LOGIN_TEMPLATE), 429

    if request.method == 'POST':
        username = request.form.get('username')
        password = request.form.get('password')

        is_user_valid = (username == app.config['ADMIN_USERNAME'])
        is_pass_valid = (password == app.config['ADMIN_PASSWORD'])

        if is_user_valid and is_pass_valid:
            session.clear()
            session['logged_in'] = True
            session['username'] = username
            session['login_time'] = datetime.now().isoformat()
            session['_csrf_token'] = secrets.token_hex(16)
            log_action("Login Success")
            return redirect('/')
        else:
            if add_login_attempt(client_ip):
                flash('Your IP has been blocked for 30 minutes.', 'error')
            else:
                flash('Invalid username or password.', 'error')
            log_action("Login Failed", f"Username: {username}")
            return render_template_string(LOGIN_TEMPLATE), 401
    
    return render_template_string(LOGIN_TEMPLATE)

@app.route('/logout')
def logout():
    log_action("Logout")
    session.clear()
    flash('You have been logged out.', 'info')
    return redirect('/login')

@app.before_request
def check_csrf():
    if request.method in ('POST', 'DELETE', 'PATCH'):
        token = session.get('_csrf_token', None)
        if not token or token != request.headers.get('X-CSRF-Token'):
            return jsonify({"error": "CSRF token mismatch"}), 400

@app.route('/')
@login_required
def dashboard():
    # Initial stats are just placeholders; they will be refreshed via API call
    stats = {
        "total_servers": "...",
        "total_users": "...",
        "total_nodes": "...",
        "api_status": "Checking"
    }
    return render_template_string(DASHBOARD_TEMPLATE, stats=stats, current_time=datetime.now())

# --- API Routes ---

@app.route('/api/status', methods=['GET'])
@login_required
@rate_limit(10, 60)
def api_status():
    _, error = api_client._request("servers?per_page=1", use_cache=False)
    if error:
        return jsonify({"status": "error", "message": error}), 500
    return jsonify({"status": "ok"})

@app.route('/api/stats', methods=['GET'])
@login_required
@rate_limit(5, 60)
def get_stats():
    # Fetch fresh data for stats
    server_data, s_err = api_client._request("servers?per_page=1", use_cache=False)
    user_data, u_err = api_client._request("users?per_page=1", use_cache=False)
    node_data, n_err = api_client._request("nodes?per_page=1", use_cache=False)
    
    stats = {
        "total_servers": server_data['meta']['pagination']['total'] if not s_err else 'N/A',
        "total_users": user_data['meta']['pagination']['total'] if not u_err else 'N/A',
        "total_nodes": node_data['meta']['pagination']['total'] if not n_err else 'N/A',
        "api_status": "Connected" if not any([s_err, u_err, n_err]) else "Error"
    }
    return jsonify({"stats": stats})

@app.route('/api/servers', methods=['GET'])
@login_required
@rate_limit()
def get_servers():
    page = request.args.get('page', 1, type=int)
    query = sanitize_input(request.args.get('q', ''))
    suspended = request.args.get('suspended', '')
    
    params = {'page': page, 'per_page': 10}
    if query:
        params['filter[name]'] = query
    if suspended == 'true':
        params['filter[suspended]'] = True
    elif suspended == 'false':
        params['filter[suspended]'] = False
        
    servers, error = api_client.get_paged_data('servers', params=params)
    if error:
        return jsonify({"error": error}), 500
    return jsonify({"servers": servers})

@app.route('/api/server/<uuid>/<action>', methods=['POST'])
@login_required
@rate_limit(10, 60)
def server_action(uuid, action):
    if not validate_uuid(uuid):
        return jsonify({"error": "Invalid server UUID"}), 400
    
    if action == 'power':
        signal = request.json.get('signal')
        if signal not in ['start', 'stop', 'restart', 'kill']:
            return jsonify({"error": "Invalid power action"}), 400
        data, error = api_client.control_server(uuid, 'power', data={"signal": signal})
        log_action("Server Power", f"UUID: {uuid}, Action: {signal}")
    elif action == 'delete':
        data, error = api_client.delete_server(uuid)
        log_action("Server Delete", f"UUID: {uuid}")
    else:
        return jsonify({"error": "Invalid action"}), 400

    if error:
        return jsonify({"error": error}), 500
    return jsonify({"status": "success", "data": data or {}})

@app.route('/api/users', methods=['GET', 'POST'])
@login_required
@rate_limit()
def handle_users():
    if request.method == 'POST':
        user_data = request.json
        required_keys = ['username', 'email', 'first_name', 'last_name', 'password']
        if not all(k in user_data for k in required_keys):
            return jsonify({"error": "Missing required user fields"}), 400
        if not validate_email(user_data['email']):
            return jsonify({"error": "Invalid email format"}), 400
        
        data, error = api_client.create_user(user_data)
        log_action("User Create", f"Username: {user_data['username']}")
        if error:
            return jsonify({"error": error}), 500
        return jsonify(data), 201

    # GET request
    users, error = api_client.get_all_data('users')
    if error:
        return jsonify({"error": error}), 500
    return jsonify({"users": users})

@app.route('/api/users/<int:user_id>', methods=['DELETE'])
@login_required
@rate_limit()
def delete_user(user_id):
    data, error = api_client.delete_user(user_id)
    log_action("User Delete", f"ID: {user_id}")
    if error:
        return jsonify({"error": error}), 500
    return jsonify({"status": "success"}), 200


@app.route('/api/nodes', methods=['GET'])
@login_required
@rate_limit()
def get_nodes():
    nodes, error = api_client.get_all_data('nodes')
    if error:
        return jsonify({"error": error}), 500
    return jsonify({"nodes": nodes})

if __name__ == '__main__':
    # Use a production-ready WSGI server like Gunicorn or Waitress instead of app.run in production
    # Example: gunicorn -w 4 -b 0.0.0.0:5001 your_script_name:app
    app.run(debug=False, host='0.0.0.0', port=5001)


