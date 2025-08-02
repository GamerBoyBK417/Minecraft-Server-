import os
import requests
from flask import Flask, render_template_string, redirect, url_for, request, flash

# --- Flask App Initialization ---
app = Flask(__name__)
# A secret key is needed for flashing messages
app.secret_key = os.urandom(24) 

# --- Pterodactyl Configuration from Environment Variables ---
PANEL_URL = os.getenv('PTERO_PANEL_URL')
API_KEY = os.getenv('PTERO_API_KEY')
SERVER_ID = os.getenv('PTERO_SERVER_ID')

# Validate that environment variables are set
if not all([PANEL_URL, API_KEY, SERVER_ID]):
    raise ValueError("Error: PTERO_PANEL_URL, PTERO_API_KEY, and PTERO_SERVER_ID environment variables must be set.")

# --- Pterodactyl API Setup ---
API_BASE_URL = f'{PANEL_URL}/api/client/servers/{SERVER_ID}'
HEADERS = {
    'Authorization': f'Bearer {API_KEY}',
    'Accept': 'application/json',
    'Content-Type': 'application/json'
}

# --- HTML Template (Embedded in Python for simplicity) ---
HTML_TEMPLATE = """
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-g">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Pterodactyl Server Control</title>
    <style>
        body { font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Helvetica, Arial, sans-serif; background-color: #f0f2f5; color: #333; margin: 0; padding: 20px; display: flex; justify-content: center; align-items: center; min-height: 100vh; }
        .container { background: white; padding: 30px; border-radius: 12px; box-shadow: 0 4px 20px rgba(0,0,0,0.1); width: 100%; max-width: 500px; text-align: center; }
        h1 { margin-top: 0; color: #1a2b4d; }
        .status { padding: 15px; border-radius: 8px; font-size: 1.2em; font-weight: bold; margin-bottom: 25px; }
        .status.running { background-color: #e8f9f0; color: #28a745; }
        .status.stopping { background-color: #fff0e3; color: #fd7e14; }
        .status.offline { background-color: #fbebee; color: #dc3545; }
        .btn-group { display: flex; gap: 10px; justify-content: center; flex-wrap: wrap; margin-bottom: 25px;}
        .btn { border: none; padding: 12px 24px; border-radius: 8px; font-size: 1em; font-weight: 600; cursor: pointer; text-decoration: none; color: white; transition: background-color 0.3s, transform 0.2s; }
        .btn:active { transform: scale(0.98); }
        .btn-start { background-color: #28a745; } .btn-start:hover { background-color: #218838; }
        .btn-stop { background-color: #dc3545; } .btn-stop:hover { background-color: #c82333; }
        .btn-restart { background-color: #007bff; } .btn-restart:hover { background-color: #0069d9; }
        .command-form { display: flex; gap: 10px; }
        .command-input { flex-grow: 1; border: 1px solid #ccc; border-radius: 8px; padding: 12px; font-size: 1em; }
        .btn-send { background-color: #6c757d; } .btn-send:hover { background-color: #5a6268; }
        .flash { padding: 12px; border-radius: 8px; margin-bottom: 20px; }
        .flash.success { background-color: #d4edda; color: #155724; }
        .flash.error { background-color: #f8d7da; color: #721c24; }
    </style>
</head>
<body>
    <div class="container">
        <h1>Server Control</h1>
        {% with messages = get_flashed_messages(with_categories=true) %}
            {% if messages %}
                {% for category, message in messages %}
                    <div class="flash {{ category }}">{{ message }}</div>
                {% endfor %}
            {% endif %}
        {% endwith %}
        {% if status %}
            <div class="status {{ status.state }}">{{ status.state.upper() }}</div>
            <p><strong>CPU:</strong> {{ status.cpu_usage }}% | <strong>Memory:</strong> {{ status.memory_usage }} MB</p>
        {% else %}
            <div class="status offline">COULD NOT CONNECT</div>
        {% endif %}

        <div class="btn-group">
            <a href="{{ url_for('send_power', command='start') }}" class="btn btn-start">Start</a>
            <a href="{{ url_for('send_power', command='restart') }}" class="btn btn-restart">Restart</a>
            <a href="{{ url_for('send_power', command='stop') }}" class="btn btn-stop">Stop</a>
        </div>

        <form action="{{ url_for('send_console') }}" method="post" class="command-form">
            <input type="text" name="command" class="command-input" placeholder="Enter console command..." required>
            <button type="submit" class="btn btn-send">Send</button>
        </form>
    </div>
</body>
</html>
"""

# --- Pterodactyl API Functions ---
def get_server_status():
    """Fetches server status and resource usage."""
    try:
        response = requests.get(f'{API_BASE_URL}/resources', headers=HEADERS, timeout=5)
        response.raise_for_status()
        attributes = response.json()['attributes']
        return {
            'state': attributes['current_state'],
            'cpu_usage': f"{attributes['resources']['cpu_absolute']:.2f}",
            'memory_usage': f"{attributes['resources']['memory_bytes'] / (1024**2):.2f}",
        }
    except requests.exceptions.RequestException:
        return None

def set_power_state(command: str):
    """Sends a power command (start, stop, restart)."""
    try:
        response = requests.post(f'{API_BASE_URL}/power', headers=HEADERS, json={'signal': command}, timeout=10)
        response.raise_for_status()
        return True, f"Command '{command}' sent successfully."
    except requests.exceptions.RequestException as e:
        error_msg = f"Failed to send '{command}' command."
        if e.response:
            error_msg += f" (API Error: {e.response.text})"
        return False, error_msg

def send_console_command(command: str):
    """Sends a command to the server console."""
    try:
        response = requests.post(f'{API_BASE_URL}/command', headers=HEADERS, json={'command': command}, timeout=10)
        response.raise_for_status()
        return True, f"Command '{command}' sent successfully."
    except requests.exceptions.RequestException as e:
        error_msg = f"Failed to send console command."
        if e.response:
            error_msg += f" (API Error: {e.response.text})"
        return False, error_msg

# --- Flask Routes ---
@app.route('/')
def index():
    """Main page, displays status and controls."""
    status_data = get_server_status()
    return render_template_string(HTML_TEMPLATE, status=status_data)

@app.route('/action/<command>')
def send_power(command):
    """Handles power action buttons."""
    if command in ['start', 'stop', 'restart', 'kill']:
        success, message = set_power_state(command)
        if success:
            flash(message, 'success')
        else:
            flash(message, 'error')
    else:
        flash("Invalid power command.", 'error')
    return redirect(url_for('index'))

@app.route('/command', methods=['POST'])
def send_console():
    """Handles the console command form submission."""
    command = request.form.get('command')
    if command:
        success, message = send_console_command(command)
        if success:
            flash(message, 'success')
        else:
            flash(message, 'error')
    else:
        flash("Command cannot be empty.", 'error')
    return redirect(url_for('index'))


# --- Run the App ---
if __name__ == '__main__':
    # To make it accessible on your network, use host='0.0.0.0'
    # For production, use a proper WSGI server like Gunicorn or Waitress
    app.run(host='0.0.0.0', port=5000, debug=True)
