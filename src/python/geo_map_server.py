#!/usr/bin/env python3

import io       # .BytesIO ()
import os       # .getenv (), .getcwd (), .path.splitext ()
import socket   # .gethostname ()
from   threading import Lock

from   flask import Flask, request, jsonify, send_file, render_template

# --- Server Setup ---

app = Flask(__name__, template_folder = os.getcwd ())

# Global storage for markers, indexed by label for easy updates
# Structure: {
#   "label_1": {"lat": 34.0522, "lon": -118.2437, "color": "bg-red-500", "label": "label_1"},
#   ...
# }
MARKERS = {}
markers_lock = Lock()

# Function to safely update a marker
def update_marker(data):
    """Updates or adds a marker in the global store."""
    if not all(k in data for k in ["label", "lat", "lon"]):
        return False, "Missing required fields: label, lat, lon"

    try:
        label = data["label"]
        lat = float(data["lat"])
        lon = float(data["lon"])
        color = data.get("color", "bg-indigo-500") # Default color if none provided

        # Validate coordinates (simple range check)
        if not (-90 <= lat <= 90 and -180 <= lon <= 180):
            return False, "Latitude must be -90 to 90, Longitude -180 to 180"

        with markers_lock:
            mDict = {
                "label": label,
                "lat": lat,
                "lon": lon,
                "color": color
            }
            if _time := data.get ('time'):
                mDict['time'] = _time
            MARKERS[label] = mDict
        return True, "Marker updated successfully"

    except ValueError:
        return False, "lat and lon must be valid numbers"

# Safely remove a marker
def remove_marker (data):
    """Removes a marker from the global store."""
    if not all(k in data for k in ["label"]):
        return False, "Missing required field: label"

    label = data["label"]

    try:
        with markers_lock:
            del MARKERS[label]
        return True, f'Marker "{label}" successfully removed'
    except KeyError:
        return False, f'Unknown marker "{label}"'

# --- API Endpoints ---

_MARKER_ACTIONS = {
    None:     update_marker,
    'delete': remove_marker,
    'remove': remove_marker
}

@app.route('/api/marker', defaults={'action': None}, methods=['POST'])
@app.route('/api/marker/<action>', methods=['POST'])
def add_or_update_marker(action):
    """Accepts JSON data to update a specific marker by label."""
    if not request.is_json:
        return jsonify({"success": False, "message": "Request must be JSON"}), 400

    if _marker_func := _MARKER_ACTIONS.get (action):
        success, message = _marker_func(request.json)
    else:
        success, message = False, f'Unknown action ("{action}")'

    if success:
        return jsonify({"success": True, "message": message}), 200
    else:
        return jsonify({"success": False, "message": message}), 400

def get_all_markers(_args):
    """Returns the current list of all markers for client polling."""
    with markers_lock:
        # Return the list of marker objects
        return jsonify(list(MARKERS.values()))

def clear_all_markers(_args):
    """Returns the current list of all markers for client polling."""
    with markers_lock:
        MARKERS.clear()
        # Return the list of marker objects
        return jsonify(list(MARKERS.values()))

_MARKERS_ACTIONS = {
    None:    get_all_markers,
    'clear': clear_all_markers
}

@app.route('/api/markers',          methods=['GET'], defaults={'action': None})
@app.route('/api/markers/<action>', methods=['GET'])
def all_markers(action):
    if _markers_func := _MARKERS_ACTIONS.get (action):
        return _markers_func(request.args)
    else:
        return jsonify([f'ERROR: unknown action ("{action}")'])

_IMG_MIME_EXTS = {
    'bmp':  'bmp',
    'jpg':  'jpeg',
    'jpeg': 'jpeg',
    'png':  'png',
    'gif':  'gif'
}

@app.route('/image/<image>', methods=['GET'])
def _getImage (image):
    if os.path.isfile (image):
        # Validate image path extension
        _, _ext = os.path.splitext (image)
        _mType = _IMG_MIME_EXTS.get (_ext[1:].lower ()) if _ext else None
        if _mType is None:
            return f'\"{image}\": unknown or missing extension', 400

        with open (image, 'rb') as _imgIn:
            _image_bytes = io.BytesIO (_imgIn.read ())
            return send_file (_image_bytes, mimetype = f'image/{_mType}')
    else:
        return f'Unknown file \"{image}\"', 400

@app.route('/')
def index():
    """Serves the main HTML page."""
    return render_template ('index.html')

# --- Run Server ---

# The server will run on http://127.0.0.1:5000/
if __name__ == '__main__':
    '''
    # Initial data for demonstration
    update_marker({"label": "NYC", "lat": 40.71, "lon": -74.01, "color": "bg-green-500"})
    update_marker({"label": "Tokyo", "lat": 35.68, "lon": 139.69, "color": "bg-red-500"})
    update_marker({"label": "London", "lat": 51.51, "lon": -0.13, "color": "bg-blue-500"})
    '''

    # Process HOST and PORT environment variables
    _host = os.getenv ('HOST', '127.0.0.1')
    if _host == '0.0.0.0':
        _host = socket.gethostname ()

    _port = os.getenv ('PORT', 5000)
    if _port:
        _port = int (_port)

    print("\n--- Map Server Started ---")
    print(f"Open your browser to http://{_host}:{_port}/")
    print("Use the POST endpoint to update markers in real-time.")

    app.run(host=_host, port=_port, debug=True, use_reloader=False) # use_reloader=False is set for compatibility with Canvas environment
