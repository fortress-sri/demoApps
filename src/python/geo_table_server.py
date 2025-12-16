import os       # .getenv ()
import socket   # .gethostname ()
from   threading import Lock

from flask import Flask, request, jsonify, render_template_string

# --- Server Setup ---

app = Flask(__name__)

# Global storage for records, indexed by label for easy updates
# Structure: {
#   "label_1": {"lat": 34.0522, "lon": -118.2437, "alt": 800.0, "delx": 1.2, "dely": 0.5, "delz": -0.1, "color": "bg-red-100", "label": "label_1"},
#   ...
# }
RECORDS = dict ()       # key: '<plane>-<ordinal>', value: <dict>
records_lock = Lock()

OH_SERVICES = dict ()   # key: '<plane>-<ordinal>', value: <services string>

# Function to safely update a record
def update_record(data):
    """Updates or adds a record in the global store."""
    required_fields = ["label", "lat", "lon", "alt", "delx", "dely", "delz"]
    if not all(k in data for k in required_fields):
        return False, f"Missing required fields: {', '.join(required_fields)}"

    try:
        label = data["label"]
        # Convert all critical values to float
        lat  = float(data["lat"])
        lon  = float(data["lon"])
        alt  = float(data.get ("alt",  0.0))
        delx = float(data.get ("delx", 0.0))
        dely = float(data.get ("dely", 0.0))
        delz = float(data.get ("delz", 0.0))
        time = float(data.get ("time", 0.0))

        # Default color handling: Use a tailwind color class for the table row
        color_class = data.get("color", "") 

        # Validate coordinates (simple range check)
        if not (-90 <= lat <= 90 and -180 <= lon <= 180):
            return False, "Latitude must be -90 to 90, Longitude -180 to 180"

        with records_lock:
            RECORDS[label] = {
                "label": label,
                "time":  time,
                "lat":   lat,
                "lon":   lon,
                "alt":   alt,
                "delx":  delx,
                "dely":  dely,
                "delz":  delz,
                "svcs":  OH_SERVICES.get (label, ''),
                # Store the color class directly for styling the table row
                "color": color_class
            }
        return True, "Record updated successfully"

    except ValueError:
        return False, "lat, lon, alt, delx, dely, delz, and time must be valid numbers"

# Updates OH services
def update_OH_services (data):
    if (_nodeData := data.get ('node_data')) and \
       (isinstance (_nodeData, dict)):
        _labels = list ()
        for _vDict in _nodeData.values ():
            if (_iSat   := _vDict.get ('ordinal', 0)) > 0  and \
               (_iPlane := _vDict.get ('plane',   0)) > 0  and \
               (_svcs   := _vDict.get ('runningServices')) and \
               isinstance (_svcs, list):
                with records_lock:
                    _label = f'leosat-{_iPlane:02d}-{_iSat:02d}'
                    OH_SERVICES[_label] = ' '.join (_svcs)
                    _labels.append (_label)

        return True, f"Successfully updated service list for {_labels}"

    return False, f"Bad input: {data}"

# --- API Endpoints ---

@app.route('/api/record', methods=['POST'])
def add_or_update_record():
    """Accepts JSON data to update a specific record by label (keeping original URL for compatibility)."""
    if not request.is_json:
        return jsonify({"success": False, "message": "Request must be JSON"}), 400

    success, message = update_record(request.json)

    if success:
        return jsonify({"success": True,  "message": message}), 200
    else:
        return jsonify({"success": False, "message": message}), 400

@app.route('/api/records', methods=['GET'])
def get_all_records():
    """Returns the current list of all records for client polling."""
    with records_lock:
        # Return the list of record objects
        return jsonify(list(RECORDS.values()))

@app.route('/api/OH_services', methods=['POST'])
def OH_services():
    """Accepts JSON data to update HIL services."""
    if not request.is_json:
        return jsonify({"success": False, "message": "Request must be JSON"}), 400

    success, message = update_OH_services(request.json)

    if success:
        return jsonify({"success": True, "message": message}), 200
    else:
        return jsonify({"success": False, "message": message}), 400


# --- Frontend HTML and JavaScript ---

HTML_TEMPLATE = """
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Real-Time Record Display Table</title>
    <!-- Load Tailwind CSS -->
    <script src="https://cdn.tailwindcss.com"></script>
    <style>
        /* Custom styles for the table */
        body { font-family: 'Inter', sans-serif; background-color: #f7fafc; }
        .table-container {
            max-width: 1000px;
        }
        .header-cell {
            cursor: pointer;
            user-select: none;
            transition: background-color 0.2s;
        }
        .header-cell:hover {
            background-color: #e5e7eb;
        }
        .header-cell.asc:after { content: ' \\25B2'; }
        .header-cell.desc:after { content: ' \\25BC'; }
        .highlight-row {
            animation: highlight-pulse 1s ease-out forwards;
        }
        @keyframes highlight-pulse {
            0% { background-color: #fef3c7; }
            100% { background-color: transparent; }
        }
    </style>
</head>
<body class="p-4 sm:p-8 flex flex-col items-center min-h-screen">

    <h1 class="text-3xl sm:text-4xl font-extrabold text-gray-800 mb-4">Real-Time Data Records</h1>
    <p class="text-md text-gray-600 mb-8 text-center">Data are updated automatically via API polling (1 second interval).</p>

    <!-- Data Table Container -->
    <div class="table-container w-full overflow-x-auto bg-white rounded-lg shadow-xl">
        <table class="min-w-full divide-y divide-gray-200">
            <thead class="bg-gray-100 sticky top-0">
                <tr>
                    <th id="sort-label" scope="col" class="header-cell px-3 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider rounded-tl-lg">Label</th>
                    <th id="sort-time"  scope="col" class="header-cell px-3 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">Time</th>
                    <th id="sort-lat"   scope="col" class="header-cell px-3 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">Lat</th>
                    <th id="sort-lon"   scope="col" class="header-cell px-3 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">Lon</th>
                    <th id="sort-alt"   scope="col" class="header-cell px-3 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">Alt</th>
                    <th id="sort-delx"  scope="col" class="header-cell px-3 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">DelX</th>
                    <th id="sort-dely"  scope="col" class="header-cell px-3 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">DelY</th>
                    <th id="sort-delz"  scope="col" class="header-cell px-3 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">DelZ</th>
                    <th id="sort-svcs"  scope="col" class="header-cell px-3 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider rounded-tr-lg">Services</th>
                </tr>
            </thead>
            <tbody id="data-table-body" class="bg-white divide-y divide-gray-100">
                <!-- Data rows will be dynamically injected here -->
            </tbody>
        </table>
        <div id="no-data-message" class="p-6 text-center text-gray-500 hidden">No records currently available.</div>
    </div>

    <!-- JavaScript Logic -->
    <script>
        const tableBody = document.getElementById('data-table-body');
        const noDataMessage = document.getElementById('no-data-message');
        let currentSort = { key: 'label', direction: 'asc' };
        let latestRecords = [];

        /**
         * Sorts the records by the specified key and direction.
         * @param {Array} records - The array of record objects.
         * @param {string} key - The key to sort by (e.g., 'label', 'lat').
         * @param {string} direction - 'asc' or 'desc'.
         * @returns {Array} The sorted array.
         */
        function sortRecords(records, key, direction) {
            return [...records].sort((a, b) => {
                const aValue = a[key];
                const bValue = b[key];
                
                if (typeof aValue === 'string') {
                    const comparison = aValue.localeCompare(bValue);
                    return direction === 'asc' ? comparison : -comparison;
                } else {
                    // Numeric comparison
                    if (aValue < bValue) return direction === 'asc' ? -1 : 1;
                    if (aValue > bValue) return direction === 'asc' ? 1 : -1;
                    return 0;
                }
            });
        }

        /**
         * Renders the records into the table body.
         * @param {Array} records - The array of records to display.
         * @param {Array} oldRecords - The previous array of records (used for highlighting).
         */
        function renderTable(records, oldRecords) {
            tableBody.innerHTML = ''; // Clear existing rows
            
            if (records.length === 0) {
                noDataMessage.classList.remove('hidden');
                return;
            }
            noDataMessage.classList.add('hidden');

            const oldRecordMap = oldRecords.reduce((acc, rec) => {
                acc[rec.label] = rec;
                return acc;
            }, {});

            records.forEach(record => {
                const row = tableBody.insertRow();
                
                // Set base class and highlight if data changed
                let rowClasses = `${record.color || ''}`;
                
                const oldData = oldRecordMap[record.label];
                let isUpdated = false;
                if (oldData) {
                    // Check if any critical data points have changed
                    isUpdated = (oldData.lat  !== record.lat  ||
                                 oldData.lon  !== record.lon  ||
                                 oldData.time !== record.time ||
                                 oldData.alt  !== record.alt  ||
                                 oldData.delx !== record.delx ||
                                 oldData.dely !== record.dely ||
                                 oldData.delz !== record.delz ||
                                 oldData.svcs !== record.svcs);
                }

                row.className = rowClasses;

                // Helper to insert a cell with formatted text
                const insertCell = (value, isNumeric = false) => {
                    const cell = row.insertCell();
                    cell.className = `px-3 py-2 whitespace-nowrap text-sm ${isNumeric ? 'text-right' : 'text-left'} text-gray-800`;
                    cell.textContent = isNumeric ? value.toFixed(4) : value;
                };

                insertCell(record.label);
                insertCell(record.time, true);
                insertCell(record.lat,  true);
                insertCell(record.lon,  true);
                insertCell(record.alt,  true);
                insertCell(record.delx, true);
                insertCell(record.dely, true);
                insertCell(record.delz, true);
                insertCell(record.svcs);
            });
        }

        /**
         * Fetches records and updates the table.
         */
        async function updateTable() {
            try {
                const response = await fetch('/api/records');
                if (!response.ok) {
                    throw new Error(`HTTP error! status: ${response.status}`);
                }
                const newRecords = await response.json();

                // Sort the new records before rendering
                const sortedRecords = sortRecords(newRecords, currentSort.key, currentSort.direction);
                
                renderTable(sortedRecords, latestRecords);
                
                // Update the latest records store for the next comparison
                latestRecords = newRecords;

            } catch (error) {
                console.error("Error fetching or updating records:", error);
            }
        }

        /**
         * Handles clicking on table headers for sorting.
         */
        function handleSort(key) {
            const headerCell = document.getElementById(`sort-${key}`);

            // Clear all sorting indicators
            document.querySelectorAll('.header-cell').forEach(cell => {
                cell.classList.remove('asc', 'desc');
            });

            // Determine new direction
            if (currentSort.key === key) {
                currentSort.direction = currentSort.direction === 'asc' ? 'desc' : 'asc';
            } else {
                currentSort.key = key;
                currentSort.direction = 'asc'; // Default to ascending when changing column
            }

            // Set new indicator
            headerCell.classList.add(currentSort.direction);

            // Re-render the current data immediately with the new sort order
            const sortedRecords = sortRecords(latestRecords, currentSort.key, currentSort.direction);
            renderTable(sortedRecords, latestRecords);
        }
        
        // Setup event listeners for sorting headers
        document.addEventListener('DOMContentLoaded', () => {
            const headers = ['label', 'time', 'lat', 'lon', 'alt', 'delx', 'dely', 'delz', 'svcs'];
            headers.forEach(key => {
                const element = document.getElementById(`sort-${key}`);
                if (element) {
                    element.addEventListener('click', () => handleSort(key));
                }
            });

            // Initial load
            updateTable();
            document.getElementById(`sort-${currentSort.key}`).classList.add(currentSort.direction);

            // Set up real-time polling every 1000 milliseconds (1 second)
            setInterval(updateTable, 1000);
        });
    </script>
</body>
</html>
"""

@app.route('/')
def index():
    """Serves the main HTML page."""
    return render_template_string(HTML_TEMPLATE)


# --- Run Server ---

# The server will run on http://127.0.0.1:5000/
if __name__ == '__main__':

    # Process HOST and PORT environment variables
    _host = os.getenv ('HOST', '127.0.0.1')
    if _host == '0.0.0.0':
        _host = socket.gethostname ()

    _port = os.getenv ('PORT', 5000)
    if _port:
        _port = int (_port)

    print("\n--- Table Server Started ---")
    print(f"Open your browser to http://{_host}:{_port}/")
    print("Use the POST endpoint to update records in real-time.")

    app.run(host=_host, port=_port, debug=True, use_reloader=False) # use_reloader=False is set for compatibility with Canvas environment
