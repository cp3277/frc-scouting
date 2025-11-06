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
import atexit

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
    """QR scanner page (previously the default)."""
    return render_template('index.html')

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


# --- Groq AI integration ---
# --- Groq AI integration ---
def ask_groq(question: str):
    client = Groq(api_key=GROQ_API_KEY)

    # Step 1: Generate SQL
    prompt = f"""
    CRITICAL: Output ONLY the SQL query. Do NOT include any explanations, markdown formatting (like ```sql), or other text.
    You are a data analyst for an FRC team. Given a user question, output a valid PostgreSQL SQL query 
    based on this schema:

    TABLE match_scouting (
    org_key TEXT,
    year INTEGER,
    event_key TEXT,
    match_key TEXT,
    match_number INTEGER,
    match_time TIMESTAMP,
    alliance TEXT,
    team_key TEXT,
    
    total_auto_points INTEGER,
    total_spr_auto INTEGER,
    total_teleop_points INTEGER,
    total_spr_teleop INTEGER,
    total_endgame_points INTEGER,
    contributed_points INTEGER,
    reliability_score INTEGER,
    defensive_score INTEGER,
    spr_points INTEGER,

    count_auto_coral INTEGER,
    count_teleop_coral INTEGER,
    count_lvl1_coral INTEGER,
    count_lvl2_coral INTEGER,
    count_lvl3_coral INTEGER,
    count_lvl4_coral INTEGER,
    count_coral INTEGER,

    count_processor_algae INTEGER,
    count_barge_algae INTEGER,
    count_dislodged_algae INTEGER,
    count_auto_algae INTEGER,
    count_teleop_algae INTEGER,
    count_algae INTEGER,

    count_teleop_pieces INTEGER,
    count_auto_pieces INTEGER,

    start_position_a BOOLEAN,
    start_position_b BOOLEAN,
    start_position_c BOOLEAN,
    start_position_d BOOLEAN,
    start_position_e BOOLEAN,
    did_starting_zone BOOLEAN,

    coral_lvl1_auto INTEGER,
    coral_lvl2_auto INTEGER,
    coral_lvl3_auto INTEGER,
    coral_lvl4_auto INTEGER,
    algae_barge_auto INTEGER,
    algae_processor_auto INTEGER,
    algae_dislodged_auto INTEGER,

    twelve_position INTEGER,
    two_position INTEGER,
    four_position INTEGER,
    six_position INTEGER,
    eight_position INTEGER,
    ten_position INTEGER,
    no_scoring_position INTEGER,

    spent_time_a NUMERIC(10,4),
    spent_time_b NUMERIC(10,4),
    spent_time_c NUMERIC(10,4),
    cycle_time NUMERIC(10,4),
    cycle_speed_factor NUMERIC(10,6),

    hit_opponent_cage BOOLEAN,
    intake_off_ground BOOLEAN,
    dropped_coral_human BOOLEAN,

    coral_lvl1_teleop INTEGER,
    coral_lvl2_teleop INTEGER,
    coral_lvl3_teleop INTEGER,
    coral_lvl4_teleop INTEGER,
    algae_barge_teleop INTEGER,
    algae_processor_teleop INTEGER,
    algae_dislodged_teleop INTEGER,

    on_cage_start TEXT,
    on_cage_end TEXT,
    endgame_cage_status TEXT,

    algae_stuck BOOLEAN,
    coral_stuck BOOLEAN,
    defense_rating TEXT,
    explain_defense TEXT,

    died_during_match BOOLEAN,
    recovered_from_freeze BOOLEAN,
    stopped_scoring BOOLEAN,
    communication_problems TEXT
);
    # --- CRITICAL LOGIC MAPPING RULE for Endgame Status ---
    # When analyzing the 'endgame_cage_status' field:
    # 1. Any value containing the substring **'Off the ground (deep cage)'** (e.g., 'Off the ground (deep cage)') **MUST** be treated as a **SUCCESSFUL** cage climb or endgame action.
    # 2. All other values must be treated as a FAILURE or INCOMPLETE attempt.
    # 3. When generating the query for success rate, use the PostgreSQL 'LIKE' operator with a wildcard, for example: `WHERE endgame_cage_status LIKE '%off the ground%'` 
    # ----------------------------------------------------
    # --- CRITICAL QUERY LIMIT INSTRUCTION ---
    # 1. If the user asks for the 'most' or 'least' of a metric, use ORDER BY on the aggregated column.
    # 2. **ONLY** use the LIMIT clause (e.g., LIMIT 1 or LIMIT 5) if the user explicitly uses words like 'top 5', 'best team', 'single team', or 'highest'.
    # 3. If the user asks for a simple aggregated list (e.g., 'all teams' scores' or 'all results'), DO NOT use the LIMIT clause.
    # ------------------------------------------
    The user asked: "{question}"
    Generate a valid, safe SQL SELECT query (PostgreSQL syntax) that retrieves relevant information.
    If the question asks for the 'most', 'least', 'average', or a total, ensure you use the appropriate aggregation function (SUM, AVG, COUNT, etc.) and use ORDER BY and LIMIT 1 to isolate the result.
    Do not include INSERT/DELETE/UPDATE/DROP/ALTER statements.
    """
    completion = client.chat.completions.create(
        model="llama-3.3-70b-versatile",
        messages=[{"role": "user", "content": prompt}],
    )
    sql_query = completion.choices[0].message.content.strip()

    # --- 💡 DEBUG & CLEANUP STEP ---
    print("--- 🔍 AI Generated SQL Query (Raw) ---")
    print(sql_query)
    print("-------------------------------------")

    # CRITICAL CLEANUP: Remove Markdown backticks (```sql ... ```) if the AI includes them
    if sql_query.startswith('```'):
        # Strip outer backticks and any optional language tag (like 'sql\n')
        sql_query = sql_query.strip('`').strip()
        if sql_query.lower().startswith('sql'):
             sql_query = sql_query.replace('sql', '', 1).strip()
        print("--- ✅ Cleaned SQL Query (Executing) ---")
        print(sql_query)
        print("---------------------------------------")
    
    # Simple Guardrail: Ensure it starts with SELECT and isn't destructive
    normalized_query = sql_query.upper().strip()
    if not normalized_query.startswith("SELECT"):
        return {"error": "AI attempted to generate a non-SELECT query. Aborting execution.", "query": sql_query}
        
    # --- End DEBUG & CLEANUP STEP ---

    # Step 2: Execute SQL
    try:
        data = run_sql_query(sql_query)
        
        # --- 💡 DEBUG STEP: Print the data results ---
        print("--- 📊 Database Query Results ---")
        print(data)
        print("---------------------------------")
        # --- End DEBUG STEP ---

    except Exception as e:
        # If the execution fails, print the full error context
        print(f"--- ❌ SQL Execution FAILED ---")
        print(f"Error: {e}")
        print(f"Failing Query: {sql_query}")
        print("---------------------------------")
        return {"error": f"SQL error: {e}", "query": sql_query}

    # Step 3: Summarize results
    summary_prompt = f"""
    The user asked: "{question}".
    SQL query result: {data}.
    Write a concise, readable summary of what this means in FRC terms.
    If the result set is empty, state clearly that no data was found for this query.
    """
    summary = client.chat.completions.create(
        model="llama-3.3-70b-versatile",
        messages=[{"role": "user", "content": summary_prompt}],
    )

    return {
        "query": sql_query,
        "data": data,
        "summary": summary.choices[0].message.content.strip(),
    }

# --- Existing scouting functions ---
def normalize_record(record: dict) -> dict:
    if not isinstance(record, dict):
        return record
    r = dict(record)
    r.pop('version', None)
    r.pop('timestamp', None)
    reef = r.pop('reef', None)
    if isinstance(reef, dict):
        for level in ['L4', 'L3', 'L2', 'L1']:
            r[f'reef_{level}'] = reef.get(level) or reef.get(level.lower())
    return r


def append_to_csv(record: dict):
    try:
        df = pd.DataFrame([record])
        if not os.path.exists(CURRENT_CSV):
            df.to_csv(CURRENT_CSV, mode='w', header=True, index=False)
            return f"Created {os.path.basename(CURRENT_CSV)}"
        existing = pd.read_csv(CURRENT_CSV)
        exisiting_columns = existing.columns.tolist()
        df = df.reindex
        combined = pd.concat([existing, df], ignore_index=True, sort=False)
        combined.to_csv(CURRENT_CSV, index=False)
        return f"Appended to {os.path.basename(CURRENT_CSV)}"
    except Exception as e:
        return f"Failed to append: {e}"

@app.route('/submit_json', methods=['POST'])
def submit_json():
    try:
        data = request.get_json()
        if not data:
            return jsonify({"error": "No JSON received"}), 400
        normalized = normalize_record(data)
        processed_data.append(normalized)
        csv_status = append_to_csv(normalized)
        return jsonify({"message": "Data recorded", "csv_status": csv_status})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route('/ask', methods=['POST'])
def ask():
    data = request.get_json()
    question = data.get("question")
    if not question:
        return jsonify({"error": "No question provided"}), 400
    response = ask_groq(question)
    return jsonify(response)

def start_ngrok():
    try:
        subprocess.run(["taskkill", "/IM", "ngrok.exe", "/F"], capture_output=True)
    except Exception:
        pass

    time.sleep(1)
    try:
        subprocess.Popen(["ngrok", "http", "https://localhost:5000"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        time.sleep(5)
        tunnel_data = requests.get("http://127.0.0.1:4040/api/tunnels").json()
        public_url = tunnel_data['tunnels'][0]['public_url']
        print(f"\nngrok tunnel active: {public_url}")
        print(f"Scanner page: {public_url}/scanner\n")
    except Exception as e:
        print(f"ngrok startup failed: {e}")
def stop_ngrok():
    try:
        subprocess.run(["taskkill", "/IM", "ngrok.exe", "/F"], capture_output=True)
        print("ngrok tunnel closed.")
    except Exception:
        print("Could not stop ngrok.")

atexit.register(stop_ngrok)

threading.Thread(target=start_ngrok, daemon=True).start()
if __name__ == '__main__':
    ssl_context = ('certs/localhost.pem', 'certs/localhost-key.pem')
    app.run(host='0.0.0.0', port=5000, debug=True, ssl_context=ssl_context)
