from flask import Flask, request, render_template, jsonify
import json
from datetime import datetime
import os
import pandas as pd
from dotenv import load_dotenv
import psycopg2
from groq import Groq
import subprocess
import threading
import time
import requests
import re

# --- Load environment variables ---
load_dotenv()
DB_URL = os.getenv("DATABASE_URL")
GROQ_API_KEY = os.getenv("GROQ_API_KEY")

app = Flask(__name__)

@app.route('/')
def frontend():
    """Main scouting frontend with AI and form."""
    return render_template('frontend.html')

@app.route('/scanner')
def scanner():
    """QR scanner page."""
    return render_template('index.html')

@app.route('/data-display')
def data_display():
    """Data display page."""
    return render_template('data_display.html')

@app.route('/get-data', methods=['GET'])
def get_data():
    """Fetch data for display."""
    # Replace with actual database or CSV fetching logic
    data = [
        {"Column 1": "Value 1", "Column 2": "Value 2", "Column 3": "Value 3"},
        {"Column 1": "Value A", "Column 2": "Value B", "Column 3": "Value C"}
    ]
    return jsonify(data)

@app.route('/query-ai', methods=['POST'])
def query_ai():
    """Handle AI queries."""
    try:
        data = request.get_json()
        print(f"[DEBUG] Received data for AI query: {data}")

        if not data or 'query' not in data:
            print("[ERROR] No query provided in the request.")
            return jsonify({"error": "No query provided."}), 400

        question = data['query']
        print(f"[DEBUG] Query extracted: {question}")

        result = ask_groq(question)
        print(f"[DEBUG] AI pipeline result: {result}")

        return jsonify(result)
    except Exception as e:
        print(f"[ERROR] Exception in /query-ai: {e}")
        return jsonify({"error": str(e)}), 500

@app.route('/fetch-database-data', methods=['GET'])
def fetch_database_data():
    """Fetch all data from the match_scouting table."""
    try:
        query = "SELECT * FROM match_scouting;"
        data = run_sql_query(query)
        return jsonify(data)
    except Exception as e:
        return jsonify({"error": str(e)})

# --- Directory setup ---
DOCS_DIR = os.path.join(os.path.expanduser('~'), 'Documents')
FRC_DATA_DIR = os.path.join(DOCS_DIR, 'FRC Scouting Data')
CSV_DIR = os.path.join(FRC_DATA_DIR, 'csv')
for d in [FRC_DATA_DIR, CSV_DIR]:
    os.makedirs(d, exist_ok=True)
CURRENT_CSV = os.path.join(CSV_DIR, "scouting_data_current.csv")
processed_data = []

# --- Database utility ---
def run_sql_query(query):
    conn = psycopg2.connect(DB_URL)
    cur = conn.cursor()
    cur.execute(query)
    columns = [desc[0] for desc in cur.description]
    rows = cur.fetchall()
    cur.close()
    conn.close()
    return [dict(zip(columns, row)) for row in rows]

# --- Groq AI integration for REBUILT 2026 ---
def ask_groq(question: str):
    client = Groq(api_key=GROQ_API_KEY)

    # Step 1: Generate SQL based on 2026 Game Rules
    prompt = f"""
    IMPORTANT: You must output ONLY a single, valid PostgreSQL SELECT statement that answers the user's question.
    - Wrap the SQL exactly between tags: <SQL>SELECT ...;</SQL>
    - Do NOT include any explanations, markdown, or extra text outside the tags.
    - If the user's request cannot be answered with a SELECT (for example any INSERT/UPDATE/DELETE/DDL or other write operation), output exactly: <SQL>NON_SELECT</SQL>

    You are a data analyst for FRC Team "Roboforce". Use the following table schema when writing SQL (Postgres dialect):

    TABLE match_scouting (
        id SERIAL PRIMARY KEY,
        match INTEGER,
        team INTEGER,
        alliance TEXT,        -- 'red' or 'blue'
        fuel_balls INTEGER,   -- Teleop Fuel (1pt each)
        auto_fuel INTEGER,    -- Auto Fuel (1pt each)
        alliance_pass INTEGER, -- Balls passed to alliance zone
        is_turreted INTEGER,  -- 1 if yes, 0 if no
        fits_trench INTEGER,  -- 1 if fits 22" trench
        climb TEXT,           -- 'no_climb', 'L1', 'L2', 'L3'
        auto_climb INTEGER,   -- 1 if L1 Auto Climb (15pts)
        defense INTEGER,      -- 1 if played defense, 0 if no
        passing INTEGER,      -- 1 if passed to teammates, 0 if no
        notes TEXT
    );

    SCORING RULES:
    1. Fuel: 1pt per ball.
    2. Teleop Climb: 'L3'=30, 'L2'=20, 'L1'=10.
    3. Auto Climb: auto_climb=1 is 15pts.
    4. Consistency: Smallest (MAX - MIN) range per team.
    5. Averages: ROUND(AVG(...), 2).

    The user asked: "{question}"
    """

    print(f"[DEBUG] Sending prompt to Groq API: {prompt}")

    try:
        completion = client.chat.completions.create(
            model="llama-3.3-70b-versatile",
            messages=[{"role": "user", "content": prompt}],
        )
        sql_query = completion.choices[0].message.content.strip()
        print(f"[DEBUG] Groq API response: {sql_query}")
    except Exception as e:
        print(f"[ERROR] Groq API call failed: {e}")
        return {"error": str(e)}

    sql_query = sql_query.replace('```sql', '').replace('```', '').strip()

    # If the model wrapped its result in <SQL> tags, extract that content; otherwise use the full output
    m = re.search(r"<SQL>(.*?)</SQL>", sql_query, flags=re.IGNORECASE | re.DOTALL)
    if m:
        sql_content = m.group(1).strip()
        print(f"[DEBUG] Extracted SQL from <SQL> tags: {sql_content}")
    else:
        sql_content = sql_query
        print(f"[DEBUG] No <SQL> tags found; using full response: {sql_content}")

    # If the model explicitly indicates a non-select result, block it
    if sql_content.strip().upper() == "NON_SELECT":
        print("[DEBUG] Model indicated NON_SELECT; blocking non-SELECT response")
        return {"error": "Non-SELECT query blocked.", "query": "NON_SELECT"}

    # Block clearly non-SELECT statements (INSERT/UPDATE/DELETE/CREATE/DROP/ALTER/TRUNCATE)
    if re.search(r"\b(INSERT|UPDATE|DELETE|CREATE|DROP|ALTER|TRUNCATE|GRANT|REVOKE)\b", sql_content, flags=re.IGNORECASE):
        print(f"[DEBUG] Forbidden SQL command detected in model output: {sql_content}")
        return {"error": "Non-SELECT query blocked.", "query": sql_content}

    # Attempt to extract the first SELECT statement
    sel = re.search(r"(?is)\bSELECT\b.*?(;|$)", sql_content)
    if not sel:
        print(f"[DEBUG] No SELECT statement found in model output: {sql_content}")
        return {"error": "Non-SELECT query blocked.", "query": sql_content}

    # Use the extracted SELECT statement (trim trailing semicolon)
    sql_query = sel.group(0).rstrip(';').strip()

    # Fix boolean * integer issues: Postgres won't allow boolean * 15
    if re.search(r"auto_climb\s*\*\s*15", sql_query, flags=re.IGNORECASE):
        fixed_sql = re.sub(r"auto_climb\s*\*\s*15",
                           "(CASE WHEN auto_climb THEN 15 ELSE 0 END)",
                           sql_query,
                           flags=re.IGNORECASE)
        print(f"[DEBUG] Transformed SQL to avoid boolean*int: {fixed_sql}")
        sql_query = fixed_sql

    # Final safety check: ensure the extracted query starts with SELECT
    if not sql_query.upper().lstrip().startswith("SELECT"):
        print(f"[DEBUG] After extraction, non-SELECT detected: {sql_query}")
        return {"error": "Non-SELECT query blocked.", "query": sql_query}

    # Step 2: Execute SQL
    try:
        data = run_sql_query(sql_query)
        print(f"[DEBUG] SQL query executed successfully. Data: {data}")
    except Exception as e:
        print(f"[ERROR] SQL query execution failed: {e}")
        return {"error": str(e), "query": sql_query}

    # Step 3: Summarize results
    summary_prompt = f"User asked: '{question}'. Results: {data}. Provide a simple and clear summary in plain English."
    print(f"[DEBUG] Sending summary prompt to Groq API: {summary_prompt}")

    try:
        summary = client.chat.completions.create(
            model="llama-3.3-70b-versatile",
            messages=[{"role": "user", "content": summary_prompt}],
        )
        summary_text = summary.choices[0].message.content.strip()
        print(f"[DEBUG] Groq API summary response: {summary_text}")
    except Exception as e:
        print(f"[ERROR] Groq API summary call failed: {e}")
        return {"error": str(e), "query": sql_query, "data": data}

    return {
        "query": sql_query,
        "data": data,
        "summary": summary_text,
    }

# Ensure the insert_data_to_db function is defined

def insert_data_to_db(record: dict):
    """Inserts data into the PostgreSQL database."""
    sql = """
    INSERT INTO match_scouting (
        match, team, alliance, fuel_balls, auto_fuel, alliance_pass,
        is_turreted, fits_trench, climb, auto_climb, notes,
        defense, passing
    ) VALUES (
        %(match)s, %(team)s, %(alliance)s, %(fuel_balls)s, %(auto_fuel)s, %(alliance_pass)s,
        %(is_turreted)s, %(fits_trench)s, %(climb)s, %(auto_climb)s, %(notes)s,
        %(defense)s, %(passing)s
    )
    """
    conn = None
    try:
        conn = psycopg2.connect(DB_URL)
        cur = conn.cursor()
        cur.execute(sql, record)
        conn.commit()
        cur.close()
        return "DB insert successful"
    except Exception as e:
        if conn: conn.rollback()
        print(f"[ERROR] Database insertion failed: {e}")
        return f"DB failed: {e}"
    finally:
        if conn: conn.close()


def append_to_csv(record: dict):
    """Append a scouting record to CURRENT_CSV with consistent columns and types.

    This mirrors the columns used by `insert_data_to_db` so CSV and DB stay aligned.
    Booleans are written as integers (1/0) for portability.
    """
    try:
        fieldnames = [
            'match', 'team', 'alliance', 'fuel_balls', 'auto_fuel', 'alliance_pass',
            'is_turreted', 'fits_trench', 'climb', 'auto_climb', 'notes',
            'defense'
        ]

        # Normalize values and ensure keys exist
        normalized = {}
        normalized['match'] = int(record.get('match') or 0)
        normalized['team'] = int(record.get('team') or 0)
        normalized['alliance'] = record.get('alliance') or ''
        normalized['fuel_balls'] = int(record.get('fuel_balls') or 0)
        normalized['auto_fuel'] = int(record.get('auto_fuel') or 0)
        normalized['alliance_pass'] = int(record.get('alliance_pass') or 0)

        # Booleans -> 1/0
        normalized['is_turreted'] = 1 if bool(record.get('is_turreted')) else 0
        normalized['fits_trench'] = 1 if bool(record.get('fits_trench')) else 0

        normalized['climb'] = record.get('climb') or 'no_climb'
        normalized['auto_climb'] = 10 if bool(record.get('auto_climb')) else 0
        normalized['notes'] = record.get('notes') or ''

        normalized['defense'] = 1 if bool(record.get('defense')) else 0

        df = pd.DataFrame([normalized], columns=fieldnames)

        # Write header if file doesn't exist or is empty
        write_header = not os.path.exists(CURRENT_CSV) or os.path.getsize(CURRENT_CSV) == 0
        if write_header:
            df.to_csv(CURRENT_CSV, mode='w', header=True, index=False)
        else:
            df.to_csv(CURRENT_CSV, mode='a', header=False, index=False)

        return "CSV updated successfully"
    except Exception as e:
        print(f"CSV Error: {e}")
        return f"Failed to append: {e}"

@app.route('/submit_json', methods=['POST'])
def submit_json():
    data = request.get_json()
    if not data:
        print("[DEBUG] No data received in /submit_json")
        return jsonify({"error": "No data"}), 400

    print(f"[DEBUG] Data received: {data}")

    if 'notes' not in data:
        data['notes'] = ""  # Default to an empty string if 'notes' is missing

    # Convert all checkbox fields to boolean
    checkbox_fields = ['is_turreted', 'defense', 'passing', 'fits_trench']
    for field in checkbox_fields:
        data[field] = bool(data.get(field, 0))

    # Convert 'auto_climb' to points (10 if true, 0 if false)
    data['auto_climb'] = 10 if bool(data.get('auto_climb', 0)) else 0

    csv_status = append_to_csv(data)
    print(f"[DEBUG] CSV status: {csv_status}")

    db_status = insert_data_to_db(data)
    print(f"[DEBUG] Database status: {db_status}")

    return jsonify({
        "csv_status": csv_status,
        "db_status": db_status
    })

@app.route('/ask', methods=['POST'])
def ask():
    question = request.get_json().get("question")
    print(f"[DEBUG] AI question received: {question}")

    result = ask_groq(question)
    print(f"[DEBUG] AI result: {result}")

    return jsonify(result)

# --- Ngrok & Startup ---
def start_ngrok():
    try:
        # Check if Ngrok is already running
        response = requests.get("http://127.0.0.1:4040/api/tunnels")
        if response.status_code == 200:
            tunnels = response.json().get("tunnels", [])
            if tunnels:
                public_url = tunnels[0]["public_url"]
                print(f"Ngrok is already running at: {public_url}")
                return
    except requests.ConnectionError:
        # Ngrok is not running, so start it
        pass

    try:
        # Updated to forward HTTP traffic instead of HTTPS to avoid malformed requests
        subprocess.Popen(["ngrok", "http", "5000", "--pooling-enabled"], stdout=subprocess.DEVNULL)
        time.sleep(5)  # Increased delay to allow Ngrok to start
        response = requests.get("http://127.0.0.1:4040/api/tunnels")
        tunnels = response.json().get("tunnels", [])
        if tunnels:
            public_url = tunnels[0]["public_url"]
            print(f"Ngrok tunnel available at: {public_url}")
        else:
            print("Ngrok started, but no tunnels were found. Check Ngrok configuration.")
    except Exception as e:
        print(f"Failed to start Ngrok: {e}")

if __name__ == '__main__':
    # Only start ngrok in the main process (not the reloader process)
    if os.environ.get('WERKZEUG_RUN_MAIN') == 'true':
        threading.Thread(target=start_ngrok, daemon=True).start()

    # Add this line to disable caching for development
    app.config['SEND_FILE_MAX_AGE_DEFAULT'] = 0

    # Bind to 127.0.0.1 for reliable localhost access (IPv4 only)
    app.run(host='127.0.0.1', port=5000, debug=True)