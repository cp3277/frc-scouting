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
    based on this schema for the 'match_scouting' table:

    TABLE match_scouting (
        id SERIAL PRIMARY KEY,
        match INTEGER,
        team INTEGER,
        alliance TEXT,       -- 'red' or 'blue'
        reef_L4 INTEGER,     -- Top level coral
        reef_L3 INTEGER,
        reef_L2 INTEGER,
        reef_L1 INTEGER,     -- Bottom level coral
        auto_peices INTEGER, -- Peices scored in autonomous
        barge_algae INTEGER,
        processor_count INTEGER,
        climb TEXT,          -- 'no_climb', 'park', 'shallow', 'deep'
        notes TEXT
    );

    # --- NEW: CRITICAL LOGIC MAPPING RULE for Rounding ---
    # When calculating an `AVG` or any other division that results in a decimal,
    # you MUST round the result to 2 decimal places using `ROUND(..., 2)`.
    # Example: `ROUND(AVG(total_points), 2) AS average_points`
    # ----------------------------------------------------

    # --- CRITICAL LOGIC MAPPING RULE for Consistency ---
    # When a user asks for "consistency", "reliability", or "predictability", you MUST use the statistical RANGE (MAX - MIN).
    # 1. "Consistency" is the difference between a team's best (MAX) and worst (MIN) performance for a metric.
    # 2. A SMALLER range (difference) is BETTER and means HIGHER consistency.
    # 3. A LARGER range (difference) is WORSE and means LOWER consistency (more volatile).
    # 4. HOW TO QUERY: To find the "most consistent" team for a metric (e.g., total points), you must GROUP BY team, calculate the range, and find the team with the SMALLEST range.
    #
    # Example: To find the "most consistent team" by total points:
    #   -- First, define the total_points calculation
    #   WITH TeamPoints AS (
    *REMOVED*
    #       ) AS total_points
    #     FROM match_scouting
    #   )
    #   -- Now, find the range for each team
    #   SELECT
    #     (MAX(total_points) - MIN(total_points)) AS consistency_range
    #   FROM TeamPoints
    #   GROUP BY team
    #   ORDER BY consistency_range ASC  -- ASC is critical: smallest range = most consistent
    #   LIMIT 1;
    # ----------------------------------------------------
    
    # --- CRITICAL LOGIC MAPPING RULE for Game Context & KPIs ---
    # 1. GAME PHASES:
    #    (auto_peices + reef_L4 + reef_L3 + reef_L2 + reef_L1 + barge_algae + processor_count)
    # 5. NOTES: The 'notes' column contains human observations (e.g., "robot died", "stuck"). Use `LIKE %...%` to find text in this column.
    # ----------------------------------------------------

    # --- CRITICAL LOGIC MAPPING RULE for Scoring Points ---
    # When a user asks for "points", "score", or "total value", you MUST calculate it using these point values:
    *REMOVED*
    # 8. `climb`: 'deep' = 12 points, 'shallow' = 6 points, 'park' = 2 points, 'no_climb' = 0 points
    #
    # Example: To find the total points for a team, you would use this SQL calculation:
    # SUM(
    #   (reef_L4 * 5) + (reef_L3 * 4) + (reef_L2 * 3) + (reef_L1 * 2) + 
    #   (auto_peices * 7) + (barge_algae * 4) + (processor_count * 6) +
    #   (CASE
    #       WHEN climb = 'deep' THEN 12
    #       WHEN climb = 'shallow' THEN 6
    #       WHEN climb = 'park' THEN 2
    #       ELSE 0
    #   END)
    # ) AS total_points
    # ----------------------------------------------------
    
    # --- CRITICAL LOGIC MAPPING RULE for Climb Status ---
    # 3. When generating the query for success rate, use the PostgreSQL IN operator, for example: `WHERE climb IN ('shallow', 'deep')` 
    # ----------------------------------------------------
    
    # --- CRITICAL QUERY LIMIT INSTRUCTION ---
    # 3. If the user asks for a simple aggregated list (e.g., 'all teams' scores' or 'all results'), DO NOT use the LIMIT clause.
    # ------------------------------------------
    
    The user asked: "{question}"
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
    ONLY if the result set is empty, state clearly that no data was found for this query.
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

def insert_data_to_db(record: dict):
    """Inserts a single, flat data record into the PostgreSQL database."""
    
    # This SQL query MUST match your table name and column names.
    # It assumes your table is named 'scouting_data' and columns match the JSON.
    sql = """
    INSERT INTO match_scouting (
        match, team, alliance, 
        reef_L4, reef_L3, reef_L2, reef_L1, 
        auto_peices, barge_algae, processor_count, 
        climb, notes
    )
    VALUES (
        %(match)s, %(team)s, %(alliance)s,
        %(reef_L4)s, %(reef_L3)s, %(reef_L2)s, %(reef_L1)s,
        %(auto_peices)s, %(barge_algae)s, %(processor_count)s,
        %(climb)s, %(notes)s
    )
    """
    
    conn = None
    try:
        # Connect to the database
        conn = psycopg2.connect(DB_URL)
        cur = conn.cursor()
        
        # Execute the query, passing the 'record' dictionary as parameters
        # This is safe from SQL injection
        cur.execute(sql, record)
        
        # Commit the transaction to save the data
        conn.commit()
        cur.close()
        
        # Success!
        print(f"Successfully inserted Team {record.get('team')} Match {record.get('match')} to DB.")
        return "DB insert successful"
        
    except Exception as e:
        # If anything goes wrong, roll back the change
        if conn:
            conn.rollback()
        print(f"DB Insert Error: {e}")
        return f"DB insert failed: {e}"
        
    finally:
        # Always close the connection
        if conn:
            conn.close()

def append_to_csv(record: dict):
    try:
        if isinstance(record, str):
            record = json.loads(record)
        flat_record = {k: (v if isinstance(v, (int, float, str)) else str(v))
                       for k, v in record.items()}

        df = pd.DataFrame([flat_record])

        if not os.path.exists(CURRENT_CSV):
            df.to_csv(CURRENT_CSV, mode='w', header=True, index=False)
            return f"Created {os.path.basename(CURRENT_CSV)}"

        existing = pd.read_csv(CURRENT_CSV)
        df = df.reindex(columns=existing.columns.union(df.columns), fill_value="")
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
        
        # The data is already perfect, as we fixed before
        normalized = data
        processed_data.append(normalized)
        
        # --- HERE'S THE CHANGE ---
        # Call both functions and get their status
        csv_status = append_to_csv(normalized)
        db_status = insert_data_to_db(normalized)
        
        # Return both statuses in the response
        return jsonify({
            "message": "Data recorded", 
            "csv_status": csv_status,
            "db_status": db_status
        })
        # -------------------------
        
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
