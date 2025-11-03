# hub/ai_query.py
import os
import psycopg2
from groq import Groq
from dotenv import load_dotenv

load_dotenv()

# --- Environment variables ---
DB_URL = os.getenv("DATABASE_URL")
GROQ_API_KEY = os.getenv("GROQ_API_KEY")

# --- Database connection ---
def run_sql_query(query):
    conn = psycopg2.connect(DB_URL)
    cur = conn.cursor()
    cur.execute(query)
    columns = [desc[0] for desc in cur.description]
    rows = cur.fetchall()
    cur.close()
    conn.close()
    return [dict(zip(columns, row)) for row in rows]

# --- AI Query Function ---
def ask_groq(question: str):
    """
    Ask Groq a natural-language question about the scouting data.
    It will generate an SQL query, execute it, and explain the result.
    """
    client = Groq(api_key=GROQ_API_KEY)

    # Prompt Groq to analyze and build a SQL query
    prompt = f"""
    You are an expert data analyst for FRC scouting.
    The database is PostgreSQL with tables like match_data, containing columns such as team_key, match_key, totalAutoPoints, totalTeleopPoints, and totalEndgamePoints.
    The user asked: "{question}"
    Generate a safe SQL query (PostgreSQL syntax) that retrieves relevant statistics.
    Only use SELECT statements.
    Return the query as plain text.
    """

    completion = client.chat.completions.create(
        model="llama3-8b-8192",
        messages=[{"role": "user", "content": prompt}],
    )
    sql_query = completion.choices[0].message.content.strip()

    try:
        data = run_sql_query(sql_query)
    except Exception as e:
        return {"error": f"SQL error: {e}", "query": sql_query}

    # Summarize results with AI
    summary_prompt = f"""
    The SQL query result is: {data}
    Write a clear, concise explanation of what this data means in terms of FRC match performance.
    """
    summary = client.chat.completions.create(
        model="llama3-8b-8192",
        messages=[{"role": "user", "content": summary_prompt}],
    )

    return {
        "query": sql_query,
        "data": data,
        "summary": summary.choices[0].message.content.strip(),
    }
