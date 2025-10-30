from flask import Flask, request, render_template, jsonify
import json
from datetime import datetime
import os
# Optional native dependencies for server-side QR decoding.
# Wrap imports so the Flask app can still start when these native
# libraries (zbar/libiconv) are not available on Windows.
try:
    import cv2
    from pyzbar.pyzbar import decode
    import numpy as np
except Exception as e:
    cv2 = None
    decode = None
    np = None
    # Log to console so user sees why server-side decoding may not work
    print('Warning: native QR decoding dependencies not available:', e)
import pandas as pd
import base64

app = Flask(__name__)

# Set up data directory in user's Documents folder
DOCS_DIR = os.path.join(os.path.expanduser('~'), 'Documents')
FRC_DATA_DIR = os.path.join(DOCS_DIR, 'FRC Scouting Data')
CSV_DIR = os.path.join(FRC_DATA_DIR, 'csv')

# Create directories if they don't exist
for d in [FRC_DATA_DIR, CSV_DIR]:
    if not os.path.exists(d):
        os.makedirs(d)
        print(f'Created directory: {d}')

# Main CSV file in Documents (persistent across runs)
CURRENT_CSV = os.path.join(CSV_DIR, "scouting_data_current.csv")

# Keep track of processed data
processed_data = []


def normalize_record(record: dict) -> dict:
    """Normalize incoming record for CSV:
    - remove 'version' and 'timestamp' if present
    - flatten a nested 'reef' dict into reef_L4..reef_L1 columns
    Returns a new dict suitable for writing to CSV.
    """
    if not isinstance(record, dict):
        return record

    r = dict(record)  # shallow copy
    # remove unwanted keys
    r.pop('version', None)
    r.pop('timestamp', None)

    # Flatten reef if present
    reef = r.pop('reef', None)
    if isinstance(reef, dict):
        # Use consistent keys reef_L4 ... reef_L1 so CSV columns are separate
        r['reef_L4'] = reef.get('L4') if reef.get('L4') is not None else reef.get('l4')
        r['reef_L3'] = reef.get('L3') if reef.get('L3') is not None else reef.get('l3')
        r['reef_L2'] = reef.get('L2') if reef.get('L2') is not None else reef.get('l2')
        r['reef_L1'] = reef.get('L1') if reef.get('L1') is not None else reef.get('l1')

    # Also handle case where frontend already sent reef_L* fields (no-op)
    return r

def save_to_csv():
    """Create a timestamped backup CSV in the Documents folder."""
    if not processed_data:
        return "No data to convert"
    
    # Convert to DataFrame
    df = pd.DataFrame(processed_data)
    
    # Generate backup CSV filename with timestamp
    timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
    backup_filename = f"frc_scouting_backup_{timestamp}.csv"
    backup_path = os.path.join(CSV_DIR, backup_filename)
    
    # Save backup CSV
    df.to_csv(backup_path, index=False)
    return f"Backup saved to Documents/FRC Scouting Data/csv/{backup_filename}"


def append_to_csv(record: dict):
    """Append a single record (dict) to the running CSV file.

    If the CSV doesn't exist yet it will be created with headers derived
    from the record's keys.
    """
    try:
        df = pd.DataFrame([record])
        # If the CSV doesn't exist yet, create it with headers
        if not os.path.exists(CURRENT_CSV):
            df.to_csv(CURRENT_CSV, mode='w', header=True, index=False)
            return f"Appended to {os.path.basename(CURRENT_CSV)}"

        # If CSV exists, ensure we preserve and merge columns.
        # Read existing CSV and concatenate so new columns (like 'climb')
        # are added to the table. This avoids appending rows that don't
        # line up with the original header.
        try:
            existing = pd.read_csv(CURRENT_CSV)
            combined = pd.concat([existing, df], ignore_index=True, sort=False)
            # Write back the combined frame (overwrites current CSV) so
            # headers include any new keys from the incoming record.
            combined.to_csv(CURRENT_CSV, index=False)
            return f"Appended to {os.path.basename(CURRENT_CSV)}"
        except Exception:
            # Fallback: append without rewriting if reading fails for any reason
            write_header = not os.path.exists(CURRENT_CSV)
            df.to_csv(CURRENT_CSV, mode='a', header=write_header, index=False)
            return f"Appended to {os.path.basename(CURRENT_CSV)} (fallback append)"

    except Exception as e:
        return f"Failed to append to CSV: {e}"

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/scan', methods=['POST'])
def scan_qr():
    try:
        # Get the image data from the request
        image_data = request.json.get('image')
        if not image_data:
            return jsonify({"error": "No image data received"}), 400
        
        # Remove the data URL prefix if present
        if 'base64,' in image_data:
            image_data = image_data.split('base64,')[1]
        
        # Decode base64 image
        img_bytes = base64.b64decode(image_data)
        nparr = np.frombuffer(img_bytes, np.uint8)
        img = cv2.imdecode(nparr, cv2.IMREAD_GRAYSCALE)
        
        # Scan for QR codes
        qr_codes = decode(img)
        
        if not qr_codes:
            return jsonify({"error": "No QR code found"}), 404
        
        # Process each QR code found
        results = []
        for qr in qr_codes:
            try:
                # Decode QR data
                data = json.loads(qr.data.decode('utf-8'))

                # Normalize (strip version/timestamp and flatten reef)
                normalized = normalize_record(data)

                # Add to processed data
                processed_data.append(normalized)
                # Append to the running CSV immediately
                csv_append_status = append_to_csv(normalized)

                results.append({
                    "status": "success",
                    "message": f"Data recorded for Team {normalized.get('team', 'unknown')} Match {normalized.get('match', 'unknown')}",
                    "csv_status": csv_append_status,
                    "data": normalized
                })
            
            except json.JSONDecodeError:
                results.append({
                    "status": "error",
                    "message": "Invalid JSON data in QR code"
                })
        
        return jsonify({
            "message": "QR code(s) processed successfully",
            "results": results
        })
    
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route('/data')
def view_data():
    """View all processed data"""
    return jsonify(processed_data)


@app.route('/submit_json', methods=['POST'])
def submit_json():
    """Accept decoded JSON payloads from clients (browser-side decoding).
    Appends directly to the running CSV.
    """
    try:
        data = request.get_json()
        if not data:
            return jsonify({"error": "No JSON payload received"}), 400

        # Normalize payload: remove version/timestamp and flatten reef
        normalized = normalize_record(data)

        # Add to processed data and append to the running CSV
        processed_data.append(normalized)
        csv_append_status = append_to_csv(normalized)

        return jsonify({
            "message": f"Data recorded for Team {normalized.get('team', 'unknown')} Match {normalized.get('match', 'unknown')}",
            "data": normalized,
            "csv_status": csv_append_status
        })

    except Exception as e:
        return jsonify({"error": str(e)}), 500

if __name__ == '__main__':
    # Use the certificates generated by mkcert (stored in certs directory)
    ssl_context = ('certs/localhost.pem', 'certs/localhost-key.pem')
    app.run(host='0.0.0.0', port=5000, debug=True, ssl_context=ssl_context)