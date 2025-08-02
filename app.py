from flask import Flask, Response, request
import requests

app = Flask(__name__)

# The base URL of the site you want to proxy.
# Using a placeholder for security and generality.
TARGET_URL = "https://gamep.cloudcrash.shop"

@app.route("/", defaults={"path": ""})
@app.route("/<path:path>", methods=["GET", "POST", "PUT", "DELETE", "PATCH", "HEAD"])
def proxy(path):
    """
    This function acts as a proxy. It forwards the incoming request from a user
    to the TARGET_URL and then sends the response from the TARGET_URL back to the user.
    """
    try:
        # Construct the full target URL
        full_url = f"{TARGET_URL}/{path}"

        # Forward most headers from the original request
        # We exclude the 'Host' header as it would be incorrect for the target server.
        headers = {key: value for (key, value) in request.headers if key.lower() != 'host'}

        # Make the request to the target server using the same method, headers, and data
        resp = requests.request(
            method=request.method,
            url=full_url,
            headers=headers,
            params=request.args,
            data=request.get_data(),
            cookies=request.cookies,
            allow_redirects=False, # It's often better to let the client handle redirects
            timeout=10 # Add a timeout for robustness
        )

        # Exclude certain headers from the response that are controlled by the proxy server
        excluded_headers = ['content-encoding', 'content-length', 'transfer-encoding', 'connection']
        response_headers = [(name, value) for (name, value) in resp.raw.headers.items()
                            if name.lower() not in excluded_headers]

        # Create and return the response to the original client
        return Response(
            resp.content,
            status=resp.status_code,
            headers=response_headers,
            content_type=resp.headers.get('Content-Type')
        )

    except requests.exceptions.RequestException as e:
        # Handle connection errors or other request issues
        return f"<h1>Proxy Error</h1><p>Could not connect to the target server: {e}</p>", 502
    except Exception as e:
        # Handle other unexpected errors
        return f"<h1>An Unexpected Error Occurred</h1><p>{str(e)}</p>", 500

if __name__ == "__main__":
    # Run the Flask app.
    # host="0.0.0.0" makes it accessible from any IP address.
    # Use debug=True for development, but turn it off for production.
    app.run(host="0.0.0.0", port=10000, debug=False)
