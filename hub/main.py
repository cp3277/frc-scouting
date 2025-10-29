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

# Ensure the data directories exist
DATA_DIR = "collected_data"
CSV_DIR = os.path.join(DATA_DIR, "csv")
JSON_DIR = os.path.join(DATA_DIR, "json")
for d in [DATA_DIR, CSV_DIR, JSON_DIR]:
    if not os.path.exists(d):
        os.makedirs(d)

# Single CSV file to collect all inputs while the server is running
CURRENT_CSV = os.path.join(CSV_DIR, "scouting_data_current.csv")

# Keep track of processed data
processed_data = []

def save_to_csv():
    """Convert all JSON data to CSV"""
    if not processed_data:
        return "No data to convert"
    
    # Convert to DataFrame
    df = pd.DataFrame(processed_data)
    
    # Generate CSV filename with timestamp
    csv_filename = f"scouting_data_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv"
    csv_path = os.path.join(CSV_DIR, csv_filename)
    
    # Save to CSV
    df.to_csv(csv_path, index=False)
    return f"Data saved to {csv_filename}"


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
                
                # Save JSON file
                timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
                json_filename = f"scout_data_{data.get('team', 'unknown')}_{data.get('match', 'unknown')}_{timestamp}.json"
                json_path = os.path.join(JSON_DIR, json_filename)
                
                with open(json_path, 'w') as f:
                    json.dump(data, f, indent=2)
                
                # Add to processed data
                processed_data.append(data)
                # Append to the running CSV immediately
                csv_append_status = append_to_csv(data)

                results.append({
                    "status": "success",
                    "message": f"Data saved to {json_filename}",
                    "csv_append_status": csv_append_status,
                    "data": data
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
    Saves the JSON, appends to processed_data and updates CSVs.
    """
    try:
        data = request.get_json()
        if not data:
            return jsonify({"error": "No JSON payload received"}), 400

        # Save JSON file
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        json_filename = f"scout_data_{data.get('team', 'unknown')}_{data.get('match', 'unknown')}_{timestamp}.json"
        json_path = os.path.join(JSON_DIR, json_filename)

        with open(json_path, 'w') as f:
            json.dump(data, f, indent=2)

        # Add to processed data and append to the running CSV
        processed_data.append(data)
        csv_append_status = append_to_csv(data)

        return jsonify({
            "message": f"Data saved to {json_filename}",
            "data": data,
            "csv_status": csv_append_status
        })

    except Exception as e:
        return jsonify({"error": str(e)}), 500

if __name__ == '__main__':
    # Use the certificates generated by mkcert
    ssl_context = ('localhost+2.pem', 'localhost+2-key.pem')
    app.run(host='0.0.0.0', port=5000, debug=True, ssl_context=ssl_context)