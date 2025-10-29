from flask import Flask, request, render_template
import json
from datetime import datetime
import os

app = Flask(__name__)

# Ensure the data directory exists
DATA_DIR = "collected_data"
if not os.path.exists(DATA_DIR):
    os.makedirs(DATA_DIR)

@app.route('/', methods=['GET'])
def index():
    return render_template('index.html')

@app.route('/submit', methods=['POST'])
def submit_data():
    try:
        # Get form data
        data = request.form.to_dict()
        
        # Add timestamp
        data['timestamp'] = datetime.now().isoformat()
        
        # Generate unique filename
        filename = f"{DATA_DIR}/scout_data_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
        
        # Save data to JSON file
        with open(filename, 'w') as f:
            json.dump(data, f, indent=4)
            
        return "Data submitted successfully!", 200
    
    except Exception as e:
        return f"Error saving data: {str(e)}", 500

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000, debug=True)